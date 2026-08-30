# Channel import production operations

Owner: platform operator. Outcome: a Telegram product post produces one reviewable
draft within three minutes without creating duplicate jobs or products.

## Workflow and state

```text
channel_post (shop_id + channel_id + message_id)
  -> received -> queued -> processing
  -> completed -> draft -> owner review -> approved/rejected
  -> failed after bounded retries -> admin retry/review
```

`connection_id + telegram_message_id` identifies the source post and
`post_id + post_version` is the idempotency key for analysis. Workers use leases,
bounded attempts and delayed retries. Approval is the human gate before publication.
Bot tokens and OpenAI credentials remain in environment/sealed storage and are never
written to logs or AI prompts.

## Live smoke test

Configure a dedicated, non-customer shop and private channel with
`CHANNEL_SMOKE_SHOP_ID` and `CHANNEL_SMOKE_CHANNEL_ID`. The daily timer sends an
identifiable product post, waits up to 180 seconds for the real Telegram polling and
OpenAI worker, verifies a draft and duplicate-delivery safety, then removes the post
and test database rows. A successful timestamp is monitored; after 36 hours the
operator receives the normal Telegram production alert.

Manual run:

```bash
docker compose exec -T bot python scripts/channel_e2e_smoke.py --keep-evidence
```

Failure recovery: inspect bot logs using the correlation ID, verify the dedicated
channel connection and AI budget, retry once manually, then pause channel import if
duplicate safety or tenant isolation is in doubt.

## Quality metrics and alert

The channel-import dashboard reports reviewed drafts, corrected drafts, correction
events, correction rate and corrected fields. The production monitor alerts after at
least 20 reviewed drafts when the lifetime manual-correction rate exceeds 40%.
Thresholds are configurable with `CHANNEL_QUALITY_MIN_REVIEWS` and
`CHANNEL_QUALITY_MAX_CORRECTION_RATE`.

## DNS cutover and rollback

Required A records point to the production server: `app`, `admin`, `platform`, and
`proxy` under `svoi-kanal.ru`. Validate before deployment:

```bash
python scripts/validate_domain_config.py --require-dns --expected-ip 141.11.209.124
```

The legacy domains remain active during cutover. Rollback consists of restoring
`PUBLIC_API_BASE` and panel URLs in `.env`, rebuilding both panels, and reloading the
previous Caddy configuration. DNS records need not be deleted for application rollback.

## Release evidence

CI requires backend tests with deprecations treated as errors, both frontend lint and
production builds, operational-script compilation, domain configuration validation,
Docker Compose validation and a single Alembic head. Production deployment remains
reversible through the existing previous-SHA trap and verified database backup.
