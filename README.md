# Simple WireGuard Control (No DB, No P2P)

This version is intentionally minimal:
- A single control plane process.
- `client.conf` generated immediately at `/session/start`.
- Peers stored in a simple JSON file.
- Peer capacity follows the configured IPv4 pool.
- Server selection is round-robin for the given country code prefix (e.g. `de`).
- Uses SSH to add peers on the selected WireGuard server.

## Run

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

## Server List
Edit `servers.json` with this schema:

```json
{
  "country_name": "Germany",
  "country_code": "de1",
  "ip": "203.0.113.10",
  "ssh_key_path": "/home/ubuntu/.ssh/wg_de1.key",
  "ssh_user": "ubuntu",
  "ssh_port": 22
}
```

Rules:
- For the same country, use increasing codes: `de1`, `de2`, `de3`.
- Frontend sends `country_code` without number, e.g. `de`.
- Selection is round-robin across matching servers.

## Endpoints

- `POST /v1/session/start`
  - Body: `{ "country_code": "de" }`.
  - Round-robin select, create peer, push via SSH, return `client.conf`.
- `POST /v1/session/ping`
  - Updates last handshake time.

## Notes
- The control plane uses `ssh` from the host machine. Ensure the host can reach each server IP.
- The SSH key path must be accessible by the control plane process.
- The WireGuard server must allow `sudo wg set` for the SSH user.
- Address allocation uses `.2` to `.253` inside each `/24` block of `ADDRESS_POOL_CIDR`. With `10.0.0.1/22`, that means `10.0.0.2` to `10.0.0.253`, then `10.0.1.2` to `10.0.1.253`, then `10.0.2.2` to `10.0.2.253`, and so on.