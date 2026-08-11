/**
 * Names for the shapes the backend sends.
 *
 * Every one of these is an alias into `schema.ts`, which is generated from the
 * backend's own OpenAPI document. Nothing here is hand-written, so a field
 * that is renamed or removed on the server becomes a compile error in the
 * components that read it, rather than `undefined` on screen.
 *
 * Regenerate with `npm run types` after `make openapi`.
 */
import type { components } from './schema';

type Schemas = components['schemas'];

export type OverviewResponse = Schemas['OverviewResponse'];
export type RoleSummary = Schemas['RoleSummary'];
export type DelegatedSummary = Schemas['DelegatedSummary'];
export type TreeEdge = Schemas['TreeEdge'];
export type KeySummary = Schemas['KeySummary'];
export type RoleDetailResponse = Schemas['RoleDetailResponse'];
export type ArtifactSummary = Schemas['ArtifactSummary'];
export type ArtifactsResponse = Schemas['ArtifactsResponse'];
export type BinSummary = Schemas['BinSummary'];
export type ArtifactBinsResponse = Schemas['ArtifactBinsResponse'];
export type StatusResponse = Schemas['StatusResponse'];
export type RootsResponse = Schemas['RootsResponse'];
export type RootVersionSummary = Schemas['RootVersionSummary'];
export type SignatureCheckSummary = Schemas['SignatureCheckSummary'];

export type ExpiryBand = Schemas['ExpiryBand'];
export type RoleStatus = Schemas['RoleStatus'];
export type RepositoryState = Schemas['RepositoryState'];
