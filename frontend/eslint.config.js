// SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
//
// SPDX-License-Identifier: MIT

/**
 * What the linter checks, and why these rules and not others.
 *
 * The backend is held to flake8, black, isort and bandit. The interface was
 * held to nothing, while carrying a disable comment for a rule no installed
 * linter enforced. This is the other half of that pair.
 *
 * The rules of hooks are the ones worth having here. A hook called
 * conditionally, or a dependency list that has gone stale, is a defect that
 * types cannot catch and that shows up as a screen quietly holding the
 * previous answer.
 */
import js from '@eslint/js';
import reactHooks from 'eslint-plugin-react-hooks';
import globals from 'globals';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  {
    // Generated from the backend's schema, and marked "do not edit".
    ignores: ['dist', 'src/api/schema.ts'],
  },
  js.configs.recommended,
  tseslint.configs.recommended,
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: { 'react-hooks': reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
    },
  },
);
