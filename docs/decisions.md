# Decisions

Choices that went a different way from the obvious one, and why. Kept short
on purpose: the reasoning belongs somewhere a reviewer can find it, not in
whoever happened to write the code.

The longer arguments about how the service reads a repository are in
[design.md](design.md). This file is for the ones a reader is most likely to
ask about because they differ from what was suggested.

---

## Vitest rather than Jest

Jest was suggested. Vitest runs the same API, uses the project's existing Vite
configuration, and needs no second toolchain to transform TypeScript. Jest
would mean adding one and keeping it in step.

Anything written for Jest runs here unchanged, so this is a swap of runner,
not of testing style.

## Playwright in Python, driven by pytest

Playwright was suggested for the interface. It is used, and it drives a real
Chromium against the compiled page. It runs from `backend/tests/e2e` rather
than from `frontend/`, for one practical reason: an end-to-end test has to
start the backend pointed at a generated TUF repository, and that generator is
Python that already exists. Driving it from Node would mean building it twice.

One runner, one language in CI, and the fixtures come for free.

The cost, stated plainly: someone looking for browser tests will look in
`frontend/` first and not find them.

## TanStack Query rather than a hook of our own

There was a hook of our own first, about sixty lines, and it worked. ESLint's
rules of hooks then found three faults in it: a ref written during a render,
and two effects writing state synchronously.

Those are the faults a query library exists to remove. Removing sixty subtle
lines is worth one dependency, and it left no rule disabled anywhere in the
project.

Nothing is treated as going stale on its own. The backend already reuses a
verified reading briefly and declines a refresh that cannot tell it anything
new, so a second cache in front of it with its own opinions would only
disagree with the first.

## `types/` only where a page has types

The layout asked for was components, endpoints, types and hooks per page.
Three of the four pages have three of those folders, because they had nothing
page-specific to put in the fourth: their types come from `api/types.ts`,
generated from the backend's schema, and their components' props are used in
one place each.

`artifacts` does have one, and has the folder: the state its hook returns is
a real contract, and the distinction it carries between "nothing matched" and
"you have not asked yet" is the kind of thing worth naming rather than
inferring.

An empty folder on the other three would make the tree look symmetrical and
tell a reader nothing.

## A hash router, not a path router

Each screen has an address: `#/roots`, `#/artifacts`, `#/status`. That is the
point of routing them at all — "look at the root history of this repository"
is a thing one person says to another, and a tab that only exists in memory
cannot carry it.

The hash is the part that needs explaining. A path router would give cleaner
addresses, `/roots` rather than `#/roots`, but a browser asks the server for
`/roots` on a reload, and the server has to answer with `index.html` for it
to work. FastAPI's `frontend()` takes a `fallback` argument that looks like
it does this; it was tested, with `fallback="index.html"`, and `/artifacts`
still returned 404. Making it work would mean a catch-all route of our own,
and a catch-all that serves HTML would also swallow requests to API paths
that do not exist, answering an API consumer's mistake with a web page.

Everything after the `#` never reaches the server, so a hash router needs no
server change and cannot take an honest 404 away from anyone.

## One service class, not several

`metadata_fetch_service.py` was the shape suggested, and the plural was
meant. There is one class instead, because the cache and its per-key lock are
state on that object and they are what stops two verification passes writing
the same trust directory at once. Several services would mean several locks
over one directory, and no test running sequentially would catch it.

See [design.md](design.md), section 11.

## Authentication is a seam, not a feature

`middleware/auth.py` enforces nothing and says so. This service is read-only
over metadata that is already published, so there is nothing here to keep from
a visitor. What changes that is write access, and the seam sits in front of
the handlers because per-role permissions are a question about the caller
rather than about the metadata.

## Pull requests larger than 500 lines

The rule asked for was under 500, and it is right for day-to-day work.

Landing a finished project does not fit it. About 9,900 reviewable lines would
be roughly twenty pull requests, which cannot be read in the time available,
and a stack that deep breaks whenever an earlier branch moves. The work is cut
into eight instead, in dependency order, six of them between 550 and 1,000
lines.

The two large ones split further if that is preferred: the tests divide into
unit, integration and browser; the last divides into the chart and the
documents.

---

## Not done, and why

**Component tests.** Eleven tests cover the two pieces with rules worth
testing on their own, the tree layout and the header verdict. The components
themselves are covered end to end, in a browser, against a real repository,
which is where a rendering fault actually shows. Per-component render tests
would add a third layer without a third kind of failure to catch.

**Accessibility beyond the basics.** The tabs are buttons rather than a
labelled tablist, and the search field has a placeholder rather than a label.
Both are worth fixing and neither is done.

**Metrics.** The service logs and exports no counters. Every request passes
one middleware stack, so they attach there without touching a route.
