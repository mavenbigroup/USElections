# Refresh relay

Lets any viewer of the board fire the full scrape without a token in the page.

1. cloudflare.com → sign up / log in (free) → Workers & Pages → Create → Create Worker. Name it `election-refresh`. Deploy the hello-world.
2. Click Edit code, replace everything with `worker.js` from this folder, Deploy.
3. Settings → Variables and Secrets → Add → type Secret, name `GH_TOKEN`, value: your fine-grained token (this repo only, Actions: Read and write). Save.
4. Copy the worker URL (looks like `https://election-refresh.<you>.workers.dev`).
5. In `index.html`, set `const RELAY_URL='https://election-refresh.<you>.workers.dev';` and commit.

The relay rate-limits to one dispatch per minute.
