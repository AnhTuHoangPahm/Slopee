import bgmSound from '../assets/sounds/tetris.mp3';
import menuSound from '../assets/sounds/menu.mp3';
import lineClearSound from '../assets/sounds/line_clear.wav';
import slamSound from '../assets/sounds/slam.wav';
import levelUp from '../assets/sounds/level_up.wav';
import gameOverSound from '../assets/sounds/game_over.wav';

// Tetris Logic Utilities

export const TETROMINOS = {
  0: { shape: [[0]], color: 'transparent' },
  I: {
    shape: [
      [0, 'I', 0, 0],
      [0, 'I', 0, 0],
      [0, 'I', 0, 0],
      [0, 'I', 0, 0]
    ],
    color: '#8cb1b1' // Muted Cyan
  },
  J: {
    shape: [
      [0, 'J', 0],
      [0, 'J', 0],
      ['J', 'J', 0]
    ],
    color: '#7685a1' // Muted Blue
  },
  L: {
    shape: [
      [0, 'L', 0],
      [0, 'L', 0],
      [0, 'L', 'L']
    ],
    color: '#bd8e68' // Muted Orange
  },
  O: {
    shape: [
      ['O', 'O'],
      ['O', 'O']
    ],
    color: '#c4c27a' // Muted Yellow
  },
  S: {
    shape: [
      [0, 'S', 'S'],
      ['S', 'S', 0],
      [0, 0, 0]
    ],
    color: '#84ad7a' // Muted Green
  },
  T: {
    shape: [
      [0, 0, 0],
      ['T', 'T', 'T'],
      [0, 'T', 0]
    ],
    color: '#9e79b5' // Muted Purple
  },
  Z: {
    shape: [
      ['Z', 'Z', 0],
      [0, 'Z', 'Z'],
      [0, 0, 0]
    ],
    color: '#ba6e6e' // Muted Red
  }
};

export const randomTetromino = () => {
  const tetrominos = 'IJLOSTZ';
  const randTetromino = tetrominos[Math.floor(Math.random() * tetrominos.length)];
  return TETROMINOS[randTetromino];
};

// Creates empty 20x10 board
export const createBoard = () =>
  Array.from(Array(20), () => new Array(10).fill([0, 'clear']));

// Collision detection
export const checkCollision = (player, board, { x: moveX, y: moveY }) => {
  for (let y = 0; y < player.tetromino.length; y += 1) {
    for (let x = 0; x < player.tetromino[y].length; x += 1) {
      // 1. Check that we're on an actual Tetromino cell
      if (player.tetromino[y][x] !== 0) {
        if (
          // 2. Check that our move is inside the game areas height (y)
          // We shouldn't go through the bottom of the play area
          !board[y + player.pos.y + moveY] ||
          // 3. Check that our move is inside the game areas width (x)
          !board[y + player.pos.y + moveY][x + player.pos.x + moveX] ||
          // 4. Check that the cell we're moving to isn't set to clear
          board[y + player.pos.y + moveY][x + player.pos.x + moveX][1] !== 'clear'
        ) {
          return true;
        }
      }
    }
  }
  return false;
};

// Matrix rotation
export const rotateMatrix = (matrix, dir) => {
  // Transpose rows to cols
  const rotatedMatrix = matrix.map((_, index) => matrix.map(col => col[index]));
  // Reverse each row to get a rotated matrix
  if (dir > 0) return rotatedMatrix.map(row => row.reverse());
  return rotatedMatrix.reverse();
};

export const audioManager = {
  bgm: null,
  lineBreak: null,
  slamming: null,
  gameOver: null,

  init: () => {
    if (audioManager.bgm) return; // Prevent double initialization in Strict Mode
    
    audioManager.bgm = new Audio(bgmSound);
    audioManager.bgm.loop = true;
    audioManager.bgm.volume = 0.3;
    audioManager.menu = new Audio(menuSound);
    audioManager.lineBreak = new Audio(lineClearSound);
    audioManager.slamming = new Audio(slamSound);
    audioManager.levelUp = new Audio(levelUp);
    audioManager.gameOver = new Audio(gameOverSound);
  },

  playBGM: () => {
    if (audioManager.bgm) audioManager.bgm.play();
  },

  pauseBGM: () => {
    if (audioManager.bgm) audioManager.bgm.pause();
  },

  stopBGM: () => {
    if (audioManager.bgm) {
      audioManager.bgm.pause();
      audioManager.bgm.currentTime = 0;
    }
  },

  playMenu: () => {
    if (audioManager.menu) {
        audioManager.menu.currentTime = 0;
        audioManager.menu.play();
    }
  },

  stopMenu: () => {
    if (audioManager.menu) {
      audioManager.menu.pause();
      audioManager.menu.currentTime = 0;
    }
  },

  playLineBreak: () => {
    if (audioManager.lineBreak) {
      audioManager.lineBreak.currentTime = 0;
      audioManager.lineBreak.play();
    }
  },

  playSlam: () => {
    if (audioManager.slamming) {
      audioManager.slamming.currentTime = 0;
      audioManager.slamming.play();
    }
  },

  playLevelUp: () => {
    if (audioManager.levelUp) {
      audioManager.levelUp.currentTime = 0;
      audioManager.levelUp.play();
    }
  },

  playGameOver: () => {
    if (audioManager.gameOver) {
      audioManager.gameOver.currentTime = 0;
      audioManager.gameOver.play();
    }
  }
};
