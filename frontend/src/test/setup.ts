// SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
//
// SPDX-License-Identifier: MIT

/**
 * One rendered tree per test.
 *
 * Testing Library renders into the document and leaves what it rendered
 * there. Without this, the second test in a file queries a page holding both
 * renders and finds two of everything.
 */
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

afterEach(cleanup);
