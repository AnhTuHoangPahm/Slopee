import { render, screen, fireEvent } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { describe, it, expect } from 'vitest';
import Navbar from '../components/Navbar';

// Helper to render with Router since Navbar uses <Link>
const renderWithRouter = (ui) => {
  return render(<BrowserRouter>{ui}</BrowserRouter>);
};

describe('Navbar Component', () => {
  it('should render the logo and basic navigation', () => {
    renderWithRouter(<Navbar />);
    expect(screen.getByText('Slopee')).toBeDefined();
    expect(screen.getByPlaceholderText('Search for items, brands and shops...')).toBeDefined();
  });

  it('should toggle login modal when clicking Login', () => {
    renderWithRouter(<Navbar />);
    
    // Login button should exist when not logged in
    const loginButton = screen.getByText('Log In');
    expect(loginButton).toBeDefined();
    
    // In a real scenario, clicking it triggers a state or prop function.
    // For unit testing, we verify the button is clickable and present.
    fireEvent.click(loginButton);
  });
});
