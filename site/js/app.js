// The index browser: one page over site-data.json. It answers "is X in here,
// under what name, at which revision", shows what could not be pinned, and
// summarizes what the index says about the flake ecosystem.
// Preact with htm tagged templates, no build step; "htm/preact" resolves
// through the import map in index.html to a pinned CDN bundle.
import { html, render, useState, useEffect, useMemo } from "htm/preact";

const DATA_FILE = "site-data.json";
const FLAKE_ATTR = "omniflake.flakes";
const PAGE = 100;
const COPY_FLASH_MS = 1200;

// Stamped in by nix/site.nix; placeholders mean a local preview.
const COMMIT = "__COMMIT__";
const STORE_PATH = "__STORE_PATH__";
const REV_ABBREV = 12;
const REPO = "https://github.com/fzakaria/omniflake";

// The four headline numbers, each with the sentence a hover explains it with.
const KPIS = [
  {
    label: "flakes indexed",
    value: (d) => d.count,
    tip: "Flakes reachable as omniflake.flakes.<name>. Each is a pinned revision with a NAR hash, fetched only when you evaluate something from it.",
  },
  {
    label: "nodes added to your flake.lock",
    value: () => 6,
    tip: "What adding omniflake as an input costs: omniflake itself plus its five foundation inputs (nixpkgs, flake-utils, systems, flake-parts, flake-compat). The indexed flakes are not inputs, so this never grows.",
  },
  {
    label: "use a lock computed by Nix",
    value: (d) => d.storedLocks,
    tip: "Flakes that ship no flake.lock, or one that no longer matches their flake.nix. Nix resolved their inputs when they were pinned, and that lock is stored here; inputs named by branch were resolved then, not when the author last tested.",
  },
  {
    label: "could not be pinned",
    value: (d) => d.failures.length,
    tip: "Flakes in the library that nix flake metadata could not lock: a deleted repository, an input that no longer resolves, a syntax error. See the 'Not pinnable' tab for each reason. Attempts that failed on GitHub's rate limit or a network error are not counted; they are retried by the next run.",
  },
];

/* ---------- helpers ---------- */

function isoDate(seconds) {
  return seconds ? new Date(seconds * 1000).toISOString().slice(0, 10) : "";
}

// Bytes at the magnitude the stats deal in: gigabytes of source tree down
// to megabytes of one.
function fmtBytes(bytes) {
  if (bytes == null) return "";
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  let n = bytes;
  let i = 0;
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024;
    i += 1;
  }
  return `${n < 10 && i > 0 ? n.toFixed(1) : Math.round(n)} ${units[i]}`;
}

// Whole-word-ish substring match over the fields a person would search by.
function matches(flake, terms) {
  const hay =
    `${flake.name} ${flake.owner}/${flake.repo} ${flake.description}`.toLowerCase();
  return terms.every((t) => hay.includes(t));
}

// Which tab the URL names. The index is the default, so an unknown or
// absent hash lands there rather than on an empty view.
function viewFromHash() {
  const h = location.hash.replace(/^#/, "");
  return h === "failures" || h === "stats" ? h : "index";
}

function useQueryParam(key) {
  const [value, setValue] = useState(
    new URLSearchParams(location.search).get(key) || "",
  );
  const update = (v) => {
    setValue(v);
    const url = new URL(location.href);
    if (v) url.searchParams.set(key, v);
    else url.searchParams.delete(key);
    history.replaceState(null, "", url);
  };
  return [value, update];
}

function Copy({ text }) {
  const [done, setDone] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setDone(true);
      setTimeout(() => setDone(false), COPY_FLASH_MS);
    });
  };
  return html`<button class="more" onClick=${copy}>
    ${done ? "copied" : "copy"}
  </button>`;
}

function Command({ text }) {
  return html`<div class="cmd">
    <code>${text}</code><${Copy} text=${text} />
  </div>`;
}

/* ---------- views ---------- */

// The inputs `flakes.<name>` replaces with yours, by exact name.
const FOUNDATIONS = [
  "nixpkgs",
  "flake-utils",
  "systems",
  "flake-parts",
  "flake-compat",
];

function Flake({ f }) {
  const [open, setOpen] = useState(false);
  const toggle = () => setOpen(!open);
  const attr = `${FLAKE_ATTR}.${f.name}`;
  const commitUrl = `https://github.com/${f.owner}/${f.repo}/commit/${f.rev}`;
  const inputs = f.inputs || [];
  // "4 direct, 8 indirect inputs" once the lock's size is known; the
  // indirect count is every node of the lock that is not a direct input.
  const inputsFact =
    f.lockNodes == null
      ? `${inputs.length} direct ${inputs.length === 1 ? "input" : "inputs"}`
      : `${inputs.length} direct, ${Math.max(f.lockNodes - inputs.length, 0)} indirect inputs`;
  return html`
    <div class="flake">
      <div
        class="row"
        role="button"
        tabindex="0"
        aria-expanded=${open}
        onClick=${toggle}
        onKeyDown=${(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            toggle();
          }
        }}
      >
        <div class="name">
          <span class="arrow" aria-hidden="true">${open ? "▾" : "▸"}</span>
          ${f.name}
          ${f.storedLock &&
          html`<span
            class="tag"
            title="ships no usable flake.lock; uses one computed by Nix"
            >computed lock</span
          >`}
        </div>
        <div class="repo">
          <a
            href="https://github.com/${f.owner}/${f.repo}"
            onClick=${(e) => e.stopPropagation()}
            >${f.owner}/${f.repo}</a
          >
          ${f.description &&
          html`<span class="muted">: ${f.description}</span>`}
        </div>
        <div class="num stars">${f.stars.toLocaleString()}</div>
        <div class="num muted date">${isoDate(f.lastModified)}</div>
      </div>
      ${open &&
      html`<div class="body">
        <div class="facts">
          <span>
            commit${" "}<a href=${commitUrl}
              ><code>${f.rev.slice(0, REV_ABBREV)}</code></a
            >${" "}from${" "}${isoDate(f.lastModified)}
          </span>
          <span>last checked ${isoDate(f.checkedAt)}</span>
          <span>${inputsFact}</span>
        </div>
        ${inputs.length > 0 &&
        html`<div class="chips">
          ${inputs.map(
            (i) =>
              html`<span
                class=${"chip" + (FOUNDATIONS.includes(i) ? " unified" : "")}
                title=${FOUNDATIONS.includes(i)
                  ? "replaced with yours under flakes.<name>"
                  : "as the flake's own lock pins it"}
                >${i}</span
              >`,
          )}
        </div>`}
        <${Command} text=${`${attr}.nixosModules.default`} />
        <${Command}
          text=${`nix run 'github:fzakaria/omniflake#flakes.${f.name}.packages.x86_64-linux.default'`}
        />
        <${Command}
          text=${`nix eval 'github:fzakaria/omniflake#pinned.${f.name}.inputs.nixpkgs.rev'`}
        />
      </div>`}
    </div>
  `;
}

function Index({ data }) {
  const [q, setQ] = useQueryParam("q");
  const [sort, setSort] = useState("stars");
  const [limit, setLimit] = useState(PAGE);

  const terms = q.toLowerCase().split(/\s+/).filter(Boolean);
  const rows = useMemo(() => {
    const hits = terms.length
      ? data.flakes.filter((f) => matches(f, terms))
      : data.flakes.slice();
    const by = {
      stars: (a, b) => b.stars - a.stars || a.name.localeCompare(b.name),
      name: (a, b) => a.name.localeCompare(b.name),
      pinned: (a, b) => b.lastModified - a.lastModified,
    }[sort];
    return hits.sort(by);
  }, [data, q, sort]);

  useEffect(() => setLimit(PAGE), [q, sort]);

  return html`
    <div class="kpis">
      ${KPIS.map(
        (k) =>
          html`<div class="kpi" title=${k.tip}>
            <div class="v">${k.value(data).toLocaleString()}</div>
            <div class="l">${k.label}</div>
          </div>`,
      )}
    </div>

    <${Command} text=${'inputs.omniflake.url = "github:fzakaria/omniflake";'} />

    <div class="controls">
      <input
        type="search"
        placeholder="search by name, owner/repo or description"
        value=${q}
        onInput=${(e) => setQ(e.target.value)}
      />
      <select value=${sort} onChange=${(e) => setSort(e.target.value)}>
        <option value="stars">by stars</option>
        <option value="name">by name</option>
        <option value="pinned">newest commit</option>
      </select>
    </div>

    <p class="muted">
      ${rows.length.toLocaleString()} ${rows.length === 1 ? "flake" : "flakes"}
    </p>

    <div class="flakes">
      <div class="head">
        <div>name</div>
        <div>repository</div>
        <div class="num">stars</div>
        <div class="num">commit</div>
      </div>
      ${rows
        .slice(0, limit)
        .map((f) => html`<${Flake} key=${f.name} f=${f} />`)}
    </div>
    ${rows.length > limit &&
    html`<button class="more" onClick=${() => setLimit(limit + PAGE)}>
      show ${Math.min(PAGE, rows.length - limit)} more of
      ${(rows.length - limit).toLocaleString()}
    </button>`}
  `;
}

/* ---------- stats ---------- */

// A magnitude-by-category row: label, proportional bar, value. A bar list
// rather than a plotted chart because every one of these is a ranking, the
// values are printed beside the bars, and nothing here needs an axis.
function Bars({
  rows,
  total,
  format = (v) => v.toLocaleString(),
  share,
  mono = true,
}) {
  const max = Math.max(...rows.map(([, v]) => v), 1);
  return html`<div class="statbars">
    ${rows.map(
      ([label, value]) => html`
        <div class="statbar" key=${label}>
          <span class=${mono ? "k mono" : "k"}>${label}</span>
          <span class="track"
            ><span class="fill" style=${`width:${(100 * value) / max}%`}></span
          ></span>
          <span class="v">
            ${format(value)}${share && total
              ? html`<span class="muted">
                  ${" "}${Math.round((100 * value) / total)}%
                </span>`
              : ""}
          </span>
        </div>
      `,
    )}
  </div>`;
}

function Section({ title, sub, children }) {
  return html`<section class="statsec">
    <h3>${title}</h3>
    ${sub && html`<p class="sub muted">${sub}</p>`} ${children}
  </section>`;
}

// A trend over the daily history rows. Hidden until there are two of them:
// one point is not a line, and a chart of it would imply a shape the data
// does not have.
function Trend({ rows, pick, title, sub, format = (v) => v.toLocaleString() }) {
  const pts = rows.map(pick);
  if (pts.length < 2 || pts.some((v) => v == null)) return null;
  const W = 640;
  const H = 120;
  const PAD = { l: 8, r: 8, t: 8, b: 8 };
  const min = Math.min(...pts);
  const max = Math.max(...pts);
  const span = max - min || 1;
  const X = (i) => PAD.l + (i / (pts.length - 1)) * (W - PAD.l - PAD.r);
  const Y = (v) => PAD.t + (1 - (v - min) / span) * (H - PAD.t - PAD.b);
  const line = pts.map((v, i) => `${i ? "L" : "M"}${X(i)},${Y(v)}`).join("");
  const area = `${line}L${X(pts.length - 1)},${H - PAD.b}L${X(0)},${H - PAD.b}Z`;

  return html`<div class="chart">
    <h3>${title}</h3>
    <p class="sub">${sub}</p>
    <figure>
      <svg viewBox=${`0 0 ${W} ${H}`} preserveAspectRatio="none" height=${H}>
        <path class="area" d=${area} />
        <path class="series" d=${line} />
        <circle
          class="enddot"
          cx=${X(pts.length - 1)}
          cy=${Y(pts[pts.length - 1])}
          r="4"
        />
      </svg>
    </figure>
    <div class="facts">
      <span>${rows[0].date}: ${format(pts[0])}</span>
      <span>
        ${rows[rows.length - 1].date}: ${format(pts[pts.length - 1])}
      </span>
    </div>
  </div>`;
}

function Stats({ data }) {
  const s = data.stats;
  if (!s)
    return html`<p class="muted">
      This index was built before the stats were recorded.
    </p>`;
  const history = data.history || [];
  const n = (v) => (v == null ? "—" : v.toLocaleString());
  const pct = (v) => (v == null ? "—" : `${v}%`);

  return html`
    <p class="muted">
      What the index says about itself, and about the flakes in it. Every number
      is computed when the site is built, from the same data the table on the
      Flakes tab is drawn from.
    </p>

    <div class="kpis">
      <div
        class="kpi"
        title="Every node of every indexed flake's lock file, added up. This is what adding them as inputs would put in your lock; as an index they cost you six."
      >
        <div class="v">${n(s.lockNodes && s.lockNodes.sum)}</div>
        <div class="l">lock nodes the index holds, against your 6</div>
      </div>
      <div
        class="kpi"
        title="Distinct NixOS/nixpkgs revisions pinned across the flakes whose lock has been summarized. One follows line replaces all of them with yours."
      >
        <div class="v">${n(s.nixpkgs && s.nixpkgs.distinct)}</div>
        <div class="l">different nixpkgs revisions pinned</div>
      </div>
      <div
        class="kpi"
        title="Distinct input names declared across the index. The ecosystem's dependency vocabulary."
      >
        <div class="v">${n(s.distinctInputs)}</div>
        <div class="l">distinct input names declared</div>
      </div>
      <div
        class="kpi"
        title="Days since the pinned revision of the middle flake was authored."
      >
        <div class="v">${n(s.freshness && s.freshness.medianAgeDays)}</div>
        <div class="l">days since the median flake last moved</div>
      </div>
    </div>

    <${Section}
      title="What one follows line reaches"
      sub=${`${n(s.withFoundation)} of ${n(data.count)} indexed flakes declare at least one of the five substituted inputs, across ${n(s.foundationEdges)} declared edges. Naming them once in your flake redirects every one.`}
    >
      <${Bars}
        rows=${s.inputs.slice(0, 20)}
        total=${data.count}
        share=${true}
      />
      <p class="muted">
        Top 20 of ${n(s.distinctInputs)} distinct names, by how many flakes
        declare them. ${n(s.noInputs)} flakes declare no inputs at all.
      </p>
    <//>

    <${Section}
      title="Lock size"
      sub=${`Median ${n(s.lockNodes && s.lockNodes.median)} nodes. These are the graphs the loader walks; none of them enters your lock file.`}
    >
      <${Bars} rows=${s.heaviest} />
      <p class="muted">The fifteen largest input graphs in the index.</p>
    <//>

    ${s.lockTypes &&
    html`<${Section}
      title="What the graphs are made of"
      sub=${`Every node of every summarized lock, by the fetcher it uses, across ${n(s.summarized)} flakes.`}
    >
      <${Bars} rows=${s.lockTypes} />
      <p class="muted">
        ${n(s.nixpkgs && s.nixpkgs.pins)} of those graphs pin NixOS/nixpkgs
        directly, at ${n(s.nixpkgs && s.nixpkgs.distinct)} different revisions —
        the median one
        dated${" "}${isoDate(s.nixpkgs && s.nixpkgs.medianLastModified)}, the
        oldest${" "}${isoDate(s.nixpkgs && s.nixpkgs.oldestLastModified)}.
      </p>
    <//>`}
    ${s.nixpkgs &&
    s.nixpkgs.wasteBytes &&
    html`<${Section}
      title="The nixpkgs you do not download"
      sub="Every flake that pins nixpkgs pins its own revision of it. Two things collapse that, and only one of them is Nix's doing."
    >
      <div class="kpis">
        <div
          class="kpi"
          title="Indexed flakes whose lock names a NixOS/nixpkgs node."
        >
          <div class="v">${n(s.nixpkgs.pins)}</div>
          <div class="l">flakes pin nixpkgs</div>
        </div>
        <div
          class="kpi"
          title="Nix fetches a locked node once per distinct revision, so identical pins already cost nothing extra."
        >
          <div class="v">${n(s.nixpkgs.distinct)}</div>
          <div class="l">distinct revisions among them</div>
        </div>
        <div
          class="kpi"
          title='With inputs.omniflake.inputs.nixpkgs.follows = "nixpkgs", every one of those is your nixpkgs instead.'
        >
          <div class="v">1</div>
          <div class="l">once you follow yours</div>
        </div>
        <div
          class="kpi"
          title=${`Distinct revisions times the closure size of one nixpkgs source tree (${fmtBytes(s.nixpkgs.treeBytes)}). Sources only — nothing built.`}
        >
          <div class="v">${fmtBytes(s.nixpkgs.wasteBytes)}</div>
          <div class="l">of nixpkgs sources, collapsed to one</div>
        </div>
      </div>
      <p class="muted">
        ${`Nix already collapses the ${n(s.nixpkgs.pins - s.nixpkgs.distinct)} pins that name a revision another flake also names. What is left is ${n(s.nixpkgs.distinct)} genuinely different trees, about ${fmtBytes(s.nixpkgs.wasteBytes)} of source, and following your own nixpkgs replaces all of them with the ${fmtBytes(s.nixpkgs.treeBytes)} you already have.`}
      </p>
    <//>`}

    <${Section}
      title="When the index last moved"
      sub="Flakes by the year of the revision pinned here, which is the last commit on their default branch when they were last checked."
    >
      <${Bars} rows=${s.byYear.map(([y, c]) => [String(y), c])} />
      ${s.freshness &&
      html`<p class="muted">
        ${n(s.freshness.d30)} moved in the last 30 days,${" "}
        ${n(s.freshness.d90)} in 90, ${n(s.freshness.d365)} in a year.
      </p>`}
    <//>

    <${Section}
      title="Attention and maintenance"
      sub=${`${n(s.stars.total)} stars across the index. The top ten flakes hold ${pct(s.stars.top10Share)} of them.`}
    >
      <${Bars}
        rows=${[
          ["1,000+ stars", s.stars.ge1000],
          ["100+ stars", s.stars.ge100],
          ["no stars", s.stars.zero],
        ]}
      />
      <p class="muted">
        ${pct(s.stars.freshSharePopular)} of the flakes with 100 or more stars
        were updated in the last year, against ${pct(s.stars.freshShareZero)} of
        those with none.
      </p>
    <//>

    ${s.failureClasses &&
    s.failureClasses.length > 0 &&
    html`<${Section}
      title="Why flakes do not pin"
      sub="The reasons Nix gave, grouped. Each one is listed with its own message on the Not pinnable tab."
    >
      <${Bars} rows=${s.failureClasses} mono=${false} />
    <//>`}

    <${Trend}
      rows=${history}
      pick=${(r) => r.count}
      title="Flakes indexed"
      sub="One point per daily update run."
    />
    <${Trend}
      rows=${history}
      pick=${(r) => r.lockNodeSum}
      title="Lock nodes the index holds"
      sub="The graph the index carries on your behalf, run by run."
    />
    ${history.length < 2 &&
    html`<p class="muted">
      ${history.length === 1
        ? "Trends need a second daily run; one row is recorded so far."
        : "Trends start once the daily run has recorded a few rows."}
    </p>`}
  `;
}

function Failures({ data }) {
  return html`
    <p class="muted">
      Flakes in the library that Nix could not lock, with the last line of its
      error. A fix in the upstream repository is picked up by the next daily
      run.${" "}${data.pending > 0 &&
      html`${data.pending} more failed on GitHub's rate limit or a network error
      and are not listed; they are retried by the next run.`}
    </p>
    <div class="failures">
      <div class="head">
        <div>name</div>
        <div>error</div>
      </div>
      ${data.failures.map(
        (f) =>
          html`<div class="row" key=${f.ref}>
            <div>
              <a
                href=${`https://github.com/${f.ref
                  .replace(/^github:/, "")
                  .split("/")
                  .slice(0, 2)
                  .join("/")}`}
                >${f.name}</a
              >
            </div>
            <div class="err">${f.error}</div>
          </div>`,
      )}
    </div>
  `;
}

function App() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [view, setView] = useState(viewFromHash());

  useEffect(() => {
    fetch(DATA_FILE)
      .then((r) =>
        r.ok
          ? r.json()
          : Promise.reject(new Error(`${DATA_FILE}: HTTP ${r.status}`)),
      )
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    const onHash = () => setView(viewFromHash());
    addEventListener("hashchange", onHash);
    return () => removeEventListener("hashchange", onHash);
  }, []);

  if (error)
    return html`<p class="muted">Could not load the index: ${error}</p>`;
  if (!data) return html`<p class="muted">Loading index…</p>`;

  return html`
    <nav>
      <a class=${view === "index" ? "active" : ""} href="#">Flakes</a>
      <a class=${view === "stats" ? "active" : ""} href="#stats">Stats</a>
      <a class=${view === "failures" ? "active" : ""} href="#failures"
        >Not pinnable</a
      >
    </nav>
    ${view === "index"
      ? html`<${Index} data=${data} />`
      : view === "stats"
        ? html`<${Stats} data=${data} />`
        : html`<${Failures} data=${data} />`}
  `;
}

render(html`<${App} />`, document.getElementById("app"));

// The footer's provenance line: which commit the data came from, and which
// store path serves it. Hidden in a local preview, where neither is known.
if (!COMMIT.startsWith("__")) {
  document.getElementById("provenance").innerHTML =
    ` · <a href="${REPO}/commit/${COMMIT}"><code>${COMMIT.slice(0, REV_ABBREV)}</code></a>` +
    (STORE_PATH.startsWith("__") ? "" : ` · <code>${STORE_PATH}</code>`);
}
