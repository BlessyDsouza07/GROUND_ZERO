# Ground Zero — About / Attribution

This is the consolidated attribution text Ground Zero's frontend and admin
dashboard should surface (e.g. an "About this data" or "Sources" screen).
It's derived from the licence terms documented per-source in
`docs/DataSources.md` — that file is the source of truth; this is the
short, user-facing version of it.

> Where a source's exact required wording matters legally (OpenStreetMap's
> ODbL and Wikipedia's CC BY-SA both do), verify the text below against
> that source's current attribution guidance before shipping — licence
> requirements are the provider's to change, not fixed by this document.

---

### Suggested on-screen text

> **Place data:** © OpenStreetMap contributors, available under the
> [Open Database License](https://opendatacommons.org/licenses/odbl/1-0/).
>
> **Enrichment content:** Includes information from
> [Wikipedia](https://en.wikipedia.org) (CC BY-SA 4.0) and
> [Wikidata](https://www.wikidata.org) (CC0).
>
> **Weather data:** Powered by [OpenWeatherMap](https://openweathermap.org/).
>
> **Tide data:** Powered by [WorldTides](https://www.worldtides.info/).
>
> Community-submitted places are reviewed by moderators before appearing
> in search results.

### Per-source detail

| Source | Required credit | Link |
|---|---|---|
| OpenStreetMap | "© OpenStreetMap contributors" | https://www.openstreetmap.org/copyright |
| Wikipedia | "Wikipedia" + link to the specific article used | https://en.wikipedia.org |
| Wikidata | Not legally required (CC0); credited anyway | https://www.wikidata.org |
| OpenWeatherMap | Link to openweathermap.org where weather is shown | https://openweathermap.org/ |
| WorldTides | Per current plan's ToS | https://www.worldtides.info/ |

### Placement

- A persistent, easy-to-find "Data Sources" or "About" link (footer or
  settings menu) satisfies most open-data attribution norms — it does not
  need to appear on every screen that shows a place.
- Any screen showing a Wikipedia-derived summary should link that specific
  summary back to its source article, since BY-SA attribution is meant to
  be traceable to the actual work reused, not just a blanket site credit.
- The admin dashboard should also show this page (or link to it) for
  internal accountability, since staff reviewing/moderating places are
  the ones most likely to need to verify a source's terms.
