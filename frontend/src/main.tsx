// SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
//
// SPDX-License-Identifier: MIT

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { App } from './App';
import './styles/main.css';

const root = document.getElementById('root');
if (!root) throw new Error('index.html is missing its root element');

/* Nothing here goes stale on its own.
 *
 * The backend already reuses a verified reading for a short window and
 * declines a refresh that cannot tell it anything new, so a second cache in
 * front of it with its own opinions would only disagree. Answers are kept
 * until something asks for them again, and the refresh button is what asks.
 */
const queries = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: Infinity,
      refetchOnWindowFocus: false,
      retry: false,
    },
  },
});

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queries}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
