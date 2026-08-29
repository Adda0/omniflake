// The index browser: one page over site-data.json. It answers "is X in here,
// under what name, at which revision", and shows what could not be pinned.
// Preact with htm tagged templates — no build step; "htm/preact" resolves
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

function Flake({ f }) {
  const [open, setOpen] = useState(false);
  const attr = `${FLAKE_ATTR}.${f.name}`;
  const commitUrl = `https://github.com/${f.owner}/${f.repo}/commit/${f.rev}`;
  return html`
    <div>
      <div class="row">
        <div class="name">
          <button class="disclose" onClick=${() => setOpen(!open)}>
            ${open ? "▾" : "▸"}
          </button>
          ${" "}${f.name}
          ${f.storedLock &&
          html`<span
            class="tag"
            title="ships no usable flake.lock; uses one computed by Nix"
            >computed lock</span
          >`}
        </div>
        <div>
          <a href="https://github.com/${f.owner}/${f.repo}"
            >${f.owner}/${f.repo}</a
          >
          ${f.description &&
          html`<span class="muted"> — ${f.description}</span>`}
        </div>
        <div class="num">${f.stars.toLocaleString()}</div>
        <div class="num muted">${isoDate(f.lastModified)}</div>
      </div>
      ${open &&
      html`<div class="body">
        <div class="links">
          pinned at
          <a href=${commitUrl}><code>${f.rev.slice(0, REV_ABBREV)}</code></a>
        </div>
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
      <div class="kpi">
        <div class="v">${data.count.toLocaleString()}</div>
        <div class="l">flakes indexed</div>
      </div>
      <div class="kpi">
        <div class="v">6</div>
        <div class="l">nodes added to your flake.lock</div>
      </div>
      <div class="kpi">
        <div class="v">${data.storedLocks.toLocaleString()}</div>
        <div class="l">use a lock computed by Nix</div>
      </div>
      <div class="kpi">
        <div class="v">${data.failures.length.toLocaleString()}</div>
        <div class="l">could not be pinned</div>
      </div>
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
        <option value="pinned">recently pinned</option>
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
        <div class="num">pinned</div>
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
