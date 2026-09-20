# apps/frontend — operator technique UI

Vite / React app for trying **Deterministic** vs **Intelligence** alignment
on the current case/site. Talks only to `apps/api` (`/api/v1/...`).

```bash
npm test --prefix apps/frontend
npm run dev --prefix apps/frontend   # :5175 → proxies /api to :8002
```
