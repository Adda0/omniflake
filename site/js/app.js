// The index browser: one page over site-data.json. It answers "is X in here,
// under what name, at which revision", and shows what could not be pinned.
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
    tip: "Flakes in the library that nix flake metadata could not lock: a deleted repository, an input that no longer resolves, a syntax error. See the 'Not pinnable' tab for each reason.",
  },
];

/* ---------- helpers ---------- */

function isoDate(seconds) {
  return seconds ? new Date(seconds * 1000).toISOString().slice(0, 10) : "";
}

// Whole-word-ish substring match over the fields a person would search by.
function matches(flake, terms) {
  const hay =
    `${flake.name} ${flake.owner}/${flake.repo} ${flake.description}`.toLowerCase();
  return terms.every((t) => hay.includes(t));
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
          <span>
            last
            checked${" "}${f.checkedAt
              ? isoDate(f.checkedAt)
              : "before dates were recorded"}
          </span>
          <span>
            ${`${inputs.length} direct ${inputs.length === 1 ? "input" : "inputs"}`}${f.lockNodes !=
              null && html`, ${f.lockNodes} nodes in its lock`}
          </span>
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

function Failures({ data }) {
  return html`
    <p class="muted">
      Flakes in the library that Nix could not lock, with the last line of its
      error. A fix in the upstream repository is picked up on the next weekly
      run.
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
  const [view, setView] = useState(
    location.hash === "#failures" ? "failures" : "index",
  );

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
    const onHash = () =>
      setView(location.hash === "#failures" ? "failures" : "index");
    addEventListener("hashchange", onHash);
    return () => removeEventListener("hashchange", onHash);
  }, []);

  if (error)
    return html`<p class="muted">Could not load the index: ${error}</p>`;
  if (!data) return html`<p class="muted">Loading index…</p>`;

  return html`
    <nav>
      <a class=${view === "index" ? "active" : ""} href="#">Flakes</a>
      <a class=${view === "failures" ? "active" : ""} href="#failures"
        >Not pinnable</a
      >
    </nav>
    ${view === "index"
      ? html`<${Index} data=${data} />`
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
