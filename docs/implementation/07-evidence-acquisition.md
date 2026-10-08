# 07 — Website and saved evidence

**Purpose:** collect a small, safe and traceable evidence set, including an offline path. **Requirements:** FR-12–16; DATA-01–03; NFR-02/04/05; UC-01/03; AT-03. **Dependencies:** 06. **Priority:** Must.

## Inputs and outputs

Inputs: validated public URL, mode, homepage/default or up to two same-domain support pages, saved UTF-8 text and PNG/JPEG image, optional original URL/collection time. Outputs: source-labelled text, titles, excerpts, screenshot/thumbnail, dimensions/viewport, hashes, URLs, timestamps and explicit warnings. Cached or uploaded evidence never says live.

## Future files and database changes

`backend/app/models/evidence.py`; `backend/app/schemas/evidence.py`; `backend/app/core/network_safety.py`; `backend/app/integrations/safe_http.py`, `safe_browser.py`, `public_proxy.py`; `backend/app/services/evidence.py`, `text_extraction.py`, `image_validation.py`; `backend/app/api/evidence.py`, `artifacts.py`; migration `007_evidence.py`; `backend/tests/unit/test_network_safety.py`, `test_images.py`; `backend/tests/integration/test_live_evidence.py`, `test_saved_evidence.py`, `test_browser_egress.py`.

Create `evidence` and durable `saved_evidence_uploads` manifests; attach saved staging uploads through opaque, expiring server tokens. Store only controlled relative keys and owner references. Add usable-review revision fields and artifact cleanup integration. Originals remain unchanged; thumbnail is derived. Implement saved mode first to unlock downstream work, then complete live acquisition before final acceptance.

## Endpoints

`POST /leads/{id}/saved-evidence`; `GET /runs/{id}/evidence`; `GET /artifacts/{evidence_id}/image`; `PATCH /evidence/{id}/review`. The analysis job selects mode and consumes the upload token. Unknown collection time remains null; import time is separate. No arbitrary path upload or download is accepted.

## Implementation steps

1. Implement public destination validation for HTTP/HTTPS only. Reject credentials, localhost aliases, forbidden literal addresses, IPv4-mapped IPv6 and any DNS answer in private, loopback, link-local, multicast, unspecified or reserved ranges. Validate every A/AAAA result. Fail closed on unresolved or mixed public/private answers.
2. Bind connections to the IP actually validated, preserving hostname for Host/SNI and TLS verification. Re-check redirects (max five), not only initial URL. DNS-check then ordinary hostname-connect is insufficient because DNS can change between them.
3. Put Playwright traffic through a validating local forward proxy that checks every HTTP request/HTTPS CONNECT and connects to an approved resolved IP. Disable proxy bypass including loopback, service workers, downloads, extensions and QUIC; block WebSockets and unexpected schemes. Browser routing is an additional resource guard, not the sole DNS-rebinding defense. No direct-network fallback is permitted. Verify this proxy configuration on Windows before declaring FR-16 met; if an egress bypass remains, fix/isolate it before live capture is accepted.
4. Fetch homepage by default, optionally discover at most two About/Services links whose normalized host equals the homepage host. No login or bypass. Stop on robots/access-denial signals where known and warn. Reject non-HTML; bound each decoded response to 2 MB and each request to 30 seconds with one retry. Prevent compressed-response expansion bypass.
5. Extract title/readable text; strip script/style, repeated navigation and obvious boilerplate conservatively. Store bounded text (proposed 30,000 characters/page), original source excerpts, truncation flags and collection time. Blank/blocked/non-HTML results produce warnings rather than invented content.
6. Capture a 1366x768 homepage at device scale 1 with a bounded load/render wait inside the 30-second navigation ceiling. Prefer a short settled delay to unlimited network-idle waits. Record browser/version/viewport, final URL and timestamp. Proposed browser limits: 100 requests tracked by Playwright and 20 MB aggregate transferred bytes enforced during proxy transfer, including HTTPS tunnel bytes. A plain CONNECT proxy cannot inspect encrypted individual responses or decoded HTML; do not claim it enforces a per-response decoded size. The separate safe text-fetch client enforces the SRS's 2 MB decoded page-content limit. Abort excess browser traffic and record a warning.
7. Validate capture/upload images before full decode: PNG/JPEG signature, actual decoder format, <=10 MB and <=20 million pixels; reject decompression bombs and unsupported animated payloads. Correct EXIF orientation on a working copy, preserve original, create thumbnail. Saved text has a proposed 1 MB limit.
8. Detect obvious HTTP error/captcha/consent overlays as warnings, not definitive detectors. A reviewer can mark unusable with reason. Missing/unusable screenshot sets CV unavailable without blocking text analysis.
9. Save validated artifacts atomically and DB stage results transactionally. Store evidence labels and provenance; cleanup abandoned uploads and temporary failed files.

## Errors and recovery

`UNSAFE_DESTINATION`, `REDIRECT_LIMIT`, `DNS_FAILURE`, `PAGE_TIMEOUT`, `PAGE_TOO_LARGE`, `NON_HTML`, `EMPTY_TEXT`, `SCREENSHOT_BLOCKED`, `INVALID_IMAGE`, `IMAGE_TOO_LARGE`. Redirect to an unsafe destination is blocked before connect. Optional-page failure retains homepage. Screenshot failure retains text and leads to partial analysis. Staging expiry reports `UPLOAD_EXPIRED`; no server file path is exposed.

## Tests and acceptance criteria

Test private/loopback/reserved IPv4/IPv6, DNS mixed answers/rebinding, redirect chains, public page embedding a private image/fetch/WebSocket, default proxy bypass and file/data navigation. Assert no forbidden connection occurred, not merely that a warning appeared. A controlled local fixture uses an exact test-only host+port allowlist; production configuration rejects that flag. Test response/image size edges and bombs, saved-manifest survival after restart, consumed-token retry and expired-unattached cleanup. Offline text/image creates equivalent inputs with Cached labels and original timestamps. Invalid screenshot does not create a high visual score. Public fixture yields text, screenshot and thumbnail within configured bounds. This establishes AT-03; all network tests must be independent of real internet sites.

## Saved-evidence milestone implemented

Migration 007, multipart uploads, durable token manifests, text/image acquisition handlers, source-labelled run evidence, unchanged original-image and thumbnail routes, usability reviews, review-aware retry/currentness and cleanup are implemented. The saved-mode validation subset of FR-13/14/15, DATA-01/02/03 and AT-03 is covered by offline tests. FR-12 and FR-16, plus live extraction/capture portions of FR-13/14 and full AT-03, remain pending the live milestone after modules 08-11. No DNS, HTTP fetch, proxy or browser capture is claimed yet. Saved image viewport/browser metadata stays null.

Uploaded/cached mode must match the upload manifest. Expiry defaults to one hour for unattached tokens. Attached evidence survives expiry for retry, with its prior evidence reviews pinned into new inputs. At most twenty unattached reservations per lead are accepted. Expired/failed writes and lead deletion enqueue controlled artifact cleanup; the worker retries cleanup up to three times, retaining failed tasks. The worker bounds text to 30,000 characters while preserving the original 1 MB upload. Public responses hide storage keys/tokens. See [the Swagger walkthrough](../phase-07-saved-evidence.md).
