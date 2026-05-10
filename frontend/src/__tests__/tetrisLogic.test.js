import { describe, it, expect } from 'vitest';
import { createBoard, checkCollision, rotateMatrix } from '../utils/tetrisLogic';

describe('Tetris Logic', () => {
  it('should create an empty 20x10 board', () => {
    const board = createBoard();
    expect(board.length).toBe(20);
    expect(board[0].length).toBe(10);
    expect(board[0][0]).toEqual([0, 'clear']);
  });

  it('should detect collisions correctly', () => {
    const board = createBoard();
    // Block at bottom right corner
    const player = {
      pos: { x: 9, y: 19 },
      tetromino: [
        ['Z', 'Z', 0],
        [0, 'Z', 'Z'],
        [0, 0, 0]
      ]
    };
    
    // Moving right should cause collision
    expect(checkCollision(player, board, { x: 1, y: 0 })).toBe(true);
    
    // Moving down should cause collision (bottom of board)
    expect(checkCollision(player, board, { x: 0, y: 1 })).toBe(true);
  });

  it('should rotate matrix correctly', () => {
    const matrix = [
      [1, 2],
      [3, 4]
    ];
    // Clockwise rotation
    const rotated = rotateMatrix(matrix, 1);
    expect(rotated).toEqual([
      [3, 1],
      [4, 2]
    ]);
  });
});
