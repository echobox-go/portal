<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/echobox-go/.github/main/profile/assets/mark-dark.svg">
    <img src="https://raw.githubusercontent.com/echobox-go/.github/main/profile/assets/mark-light.svg" alt="echobox-go" width="96">
  </picture>
</p>

<h1 align="center">portal</h1>

<p align="center"><b>The echobox-go web portal</b> for profiles, builds, downloads and per-stick keys.</p>

---

FastAPI, server rendered, no JavaScript build step. Runs on `eb-portal` behind
Pangolin SSO; deployment is in the builder repo (`infra/portal/compose.yaml`).

```sh
pip install -r requirements-dev.txt
make test
make dev            # http://127.0.0.1:8000 as niklas, editing ../builder/profiles/users
```

`schema/profile.schema.json` is a copy of the builder repo's
`profiles/schema/profile.schema.json`. A test checks they match when the
builder repo is cloned next to this one.

## Identity

Pangolin forwards `Remote-User` after SSO. Configure the Pangolin resource to
also inject `X-Ebox-Proxy-Token: <secret>` and give the portal the same secret
in `EBOX_PROXY_TOKEN`. Without a matching token the portal ignores
`Remote-User`, so anything that reaches the container directly gets no identity.
`EBOX_DEV_USER` is for local development only and is ignored once
`EBOX_PROXY_TOKEN` is set.

## Status

| Feature | State |
|---|---|
| Profile form and JSON API (`/api/profiles/<user>`) | Works, validates against the schema, writes `profile.yaml` |
| Commit to Forgejo (triggers ISO build) | TODO, phase 4 |
| Build status and ISO downloads | TODO, phase 4 |
| Enrolment codes, per-device tokens, revoke | TODO, phase 2 (`/api/agent/*` return 501) |

Part of [echobox-go](https://github.com/echobox-go): [`ebox`](https://github.com/echobox-go/ebox) · [`builder`](https://github.com/echobox-go/builder) · `portal`
