import { vi } from 'vitest';

// Global fetch mock
global.fetch = vi.fn((url) => {
  if (url.includes('/api/products')) {
    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve({
        items: [
          { id: 1, name: 'Mock Product 1', price: 9.99 },
          { id: 2, name: 'Mock Product 2', price: 19.99 }
        ]
      })
    });
  }
  
  return Promise.resolve({
    ok: true,
    json: () => Promise.resolve({})
  });
});
