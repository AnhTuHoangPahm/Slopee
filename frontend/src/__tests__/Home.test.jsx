import { render, screen, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { describe, it, expect, beforeAll } from 'vitest';
import Home from '../pages/Home';
import './setup'; // Import the mock setup

const renderWithRouter = (ui) => {
  return render(<BrowserRouter>{ui}</BrowserRouter>);
};

describe('Home Page Integration', () => {
  it('should fetch and display products from the API mock', async () => {
    renderWithRouter(<Home />);
    
    // Initially, it might show loading or just empty until fetch resolves
    // Wait for the mock products to appear in the DOM
    await waitFor(() => {
      expect(screen.getByText('Mock Product 1')).toBeDefined();
      expect(screen.getByText('Mock Product 2')).toBeDefined();
    });
    
    // Ensure fetch was actually called
    expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining('/api/products'));
  });
});
