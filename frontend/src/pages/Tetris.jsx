import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { createBoard, checkCollision, randomTetromino, TETROMINOS, rotateMatrix, audioManager } from '../utils/tetrisLogic';
import '../assets/tetris.css';

// Custom hook for intervals
function useInterval(callback, delay) {
  const savedCallback = useRef();
  useEffect(() => { savedCallback.current = callback; }, [callback]);
  useEffect(() => {
    function tick() { savedCallback.current(); }
    if (delay !== null) {
      const id = setInterval(tick, delay);
      return () => clearInterval(id);
    }
  }, [delay]);
}

const DIFFICULTY_SPEEDS = [1000, 900, 800, 700, 600, 500, 420, 350, 300, 265];

export default function Tetris() {
  const navigate = useNavigate();
  const wrapperRef = useRef(null);
  const [gameState, setGameState] = useState('start'); // start, playing, paused, game_over
  const [dropTime, setDropTime] = useState(null);
  const [initialDifficulty, setInitialDifficulty] = useState(1);
  const [difficulty, setDifficulty] = useState(1);
  const [lines, setLines] = useState(0);
  const [score, setScore] = useState(0);

  const [player, setPlayer] = useState({
    pos: { x: 0, y: 0 },
    tetromino: TETROMINOS[0].shape,
    collided: false,
  });

  const [nextPiece, setNextPiece] = useState(randomTetromino());
  const [board, setBoard] = useState(createBoard());
  const [clearingRows, setClearingRows] = useState([]);

  // Audio initialization on mount
  useEffect(() => {
    audioManager.init();
    return () => audioManager.stopBGM();
  }, []);

  // Play short menu theme
  useEffect(() => {
    if (gameState === 'start') audioManager.playMenu();
  }, [gameState])

  const updatePlayerPos = ({ x, y, collided }) => {
    setPlayer(prev => ({
      ...prev,
      pos: { x: prev.pos.x + x, y: prev.pos.y + y },
      collided,
    }));
  };

  const resetPlayer = useCallback(() => {
    setPlayer({
      pos: { x: Math.floor(10 / 2) - 1, y: 0 },
      tetromino: nextPiece.shape,
      collided: false,
    });
    setNextPiece(randomTetromino());
  }, [nextPiece]);

  const sweepRows = newBoard => {
    let rowsCleared = 0;
    const swept = newBoard.reduce((acc, row, index) => {
      // If a row contains no 0s, it's a full row
      if (row.findIndex(cell => cell[0] === 0) === -1) {
        rowsCleared += 1;
        setClearingRows(prev => [...prev, index]); // Trigger flash animation
        acc.unshift(new Array(10).fill([0, 'clear']));
        return acc;
      }
      acc.push(row);
      return acc;
    }, []);

    if (rowsCleared > 0) {
      audioManager.playLineBreak();

      // Standard Tetris scoring multiplier for multi-line clears
      const linePoints = [0, 100, 300, 500, 800];
      setScore(prev => prev + (linePoints[rowsCleared] * difficulty));

      setLines(prevLines => {
        const newTotalLines = prevLines + rowsCleared;
        // Check if we crossed a multiple of 10 threshold
        const levelsGained = Math.floor(newTotalLines / 10) - Math.floor(prevLines / 10);

        if (levelsGained > 0) {
          setDifficulty(prevDiff => {
            const nextDiff = Math.min(prevDiff + levelsGained, 10);
            setDropTime(DIFFICULTY_SPEEDS[nextDiff - 1]);
            return nextDiff;
          });
          audioManager.playLevelUp();
        }
        return newTotalLines;
      });

      setTimeout(() => { setClearingRows([]); }, 200);
    }
    return swept;
  };

  // Controls
  const movePlayer = dir => {
    if (!checkCollision(player, board, { x: dir, y: 0 })) {
      updatePlayerPos({ x: dir, y: 0 });
    }
  };

  const drop = () => {
    if (!checkCollision(player, board, { x: 0, y: 1 })) {
      updatePlayerPos({ x: 0, y: 1, collided: false });
    } else {
      if (player.pos.y < 1) {
        setGameState('game_over');
        setDropTime(null);
        audioManager.stopBGM();
        audioManager.playGameOver();
      }

      const newBoard = board.map(row => [...row]);
      player.tetromino.forEach((row, y) => {
        row.forEach((value, x) => {
          if (value !== 0) {
            if (newBoard[y + player.pos.y] && newBoard[y + player.pos.y][x + player.pos.x]) {
              newBoard[y + player.pos.y][x + player.pos.x] = [value, 'merged'];
            }
          }
        });
      });
      setBoard(sweepRows(newBoard));
      resetPlayer();
    }
  };

  const softDrop = () => {
    setDropTime(null);
    drop();
  };

  const keyUp = ({ keyCode }) => {
    if (gameState === 'playing' && (keyCode === 40 || keyCode === 83)) { // Down Arrow or S
      setDropTime(DIFFICULTY_SPEEDS[difficulty - 1]);
    }
  };

  const hardDrop = () => {
    let tempY = 0;
    while (!checkCollision(player, board, { x: 0, y: tempY + 1 })) {
      tempY += 1;
    }

    const newBoard = board.map(row => [...row]);
    player.tetromino.forEach((row, y) => {
      row.forEach((value, x) => {
        if (value !== 0) {
          if (newBoard[y + player.pos.y + tempY] && newBoard[y + player.pos.y + tempY][x + player.pos.x]) {
            newBoard[y + player.pos.y + tempY][x + player.pos.x] = [value, 'merged'];
          }
        }
      });
    });
    setBoard(sweepRows(newBoard));
    resetPlayer();
    audioManager.playSlam();

    if (gameState === 'playing') {
      setDropTime(null);
      setTimeout(() => setDropTime(DIFFICULTY_SPEEDS[difficulty - 1]), 10);
    }
  };

  const playerRotate = () => {
    const clonedPlayer = JSON.parse(JSON.stringify(player));
    clonedPlayer.tetromino = rotateMatrix(clonedPlayer.tetromino, 1);

    // Wall kick
    const pos = clonedPlayer.pos.x;
    let offset = 1;
    while (checkCollision(clonedPlayer, board, { x: 0, y: 0 })) {
      clonedPlayer.pos.x += offset;
      offset = -(offset + (offset > 0 ? 1 : -1));
      if (offset > clonedPlayer.tetromino[0].length) {
        // Rotate back if wall kick fails
        rotateMatrix(clonedPlayer.tetromino, -1);
        clonedPlayer.pos.x = pos;
        return;
      }
    }
    setPlayer(clonedPlayer);
  };

  const move = ({ keyCode, key }) => {
    if (gameState !== 'playing') return;

    // Left
    if (keyCode === 37) movePlayer(-1);
    // Right
    else if (keyCode === 39) movePlayer(1);
    // Down (Soft Drop)
    else if (keyCode === 40) softDrop();
    // Space (Hard Drop)
    else if (keyCode === 32) hardDrop();
    // Rotate (R or Up Arrow)
    else if (keyCode === 38 || key.toLowerCase() === 'r') playerRotate();
  };

  // Game Loop
  useInterval(() => {
    drop();
  }, dropTime);

  const startGame = () => {
    setBoard(createBoard());
    setDifficulty(initialDifficulty);
    setDropTime(DIFFICULTY_SPEEDS[initialDifficulty - 1]);
    resetPlayer();
    setScore(0);
    setLines(0);
    setGameState('playing');
    audioManager.stopMenu();
    audioManager.playBGM();
    setTimeout(() => {
      if (wrapperRef.current) wrapperRef.current.focus();
    }, 50);
  };

  const togglePause = (e) => {
    if (e && e.target && e.target.blur) e.target.blur(); // Drop focus so spacebar doesn't trigger it again

    if (gameState === 'playing') {
      setDropTime(null);
      setGameState('paused');
      audioManager.pauseBGM();
      setTimeout(() => {
        if (wrapperRef.current) wrapperRef.current.focus();
      }, 50);
    } else if (gameState === 'paused') {
      setDropTime(DIFFICULTY_SPEEDS[difficulty - 1]);
      setGameState('playing');
      audioManager.playBGM();
      setTimeout(() => {
        if (wrapperRef.current) wrapperRef.current.focus();
      }, 50);
    }
  };

  const quitGame = () => {
    setDropTime(null);
    setGameState('start');
    audioManager.stopBGM();
  };

  return (
    <div className="tetris-wrapper" ref={wrapperRef} role="button" tabIndex="0" onKeyDown={move} onKeyUp={keyUp}>

      {/* START SCREEN */}
      {gameState === 'start' && (
        <div className="tetris-start-screen">
          <div className="tetris-title">
            <span style={{ color: '#ba6e6e' }}>T</span>
            <span style={{ color: '#c4c27a' }}>E</span>
            <span style={{ color: '#8cb1b1' }}>T</span>
            <span style={{ color: '#bd8e68' }}>R</span>
            <span style={{ color: '#9e79b5' }}>I</span>
            <span style={{ color: '#84ad7a' }}>S</span>
          </div>

          <button className="tetris-menu-btn" onClick={startGame}>PLAY</button>
          <button className="tetris-menu-btn" onClick={() => setGameState('settings')}>SETTINGS</button>
          <button className="tetris-menu-btn" onClick={() => navigate('/')}>QUIT</button>
        </div>
      )}

      {/* SETTINGS SCREEN */}
      {gameState === 'settings' && (
        <div className="tetris-start-screen">
          <div className="tetris-title">SETTINGS</div>
          <div className="tetris-settings-panel">
            <label style={{ fontSize: '24px', display: 'block', marginBottom: '20px' }}>
              DIFFICULTY LEVEL: {initialDifficulty}
            </label>
            <input
              type="range"
              min="1" max="10"
              value={initialDifficulty}
              onChange={e => setInitialDifficulty(parseInt(e.target.value))}
              style={{ width: '200px', cursor: 'pointer' }}
            />
          </div>
          <button className="tetris-menu-btn" onClick={() => setGameState('start')} style={{ marginTop: '40px' }}>BACK</button>
        </div>
      )}

      {/* GAME OVER SCREEN */}
      {gameState === 'game_over' && (
        <div className="tetris-start-screen">
          <div className="tetris-title" style={{ color: '#ba6e6e' }}>GAME OVER</div>
          <div style={{ fontSize: '30px', margin: '20px 0' }}>SCORE: {score}</div>
          <button className="tetris-menu-btn" onClick={startGame}>RESTART</button>
          <button className="tetris-menu-btn" onClick={quitGame}>MAIN MENU</button>
        </div>
      )}

      {/* ACTIVE GAME UI */}
      {(gameState === 'playing' || gameState === 'paused') && (
        <div className="tetris-game-container">

          {/* Main Board */}
          <div style={{ position: 'relative' }}>
            <div className="tetris-board">
              {board.map((row, y) => row.map((cell, x) => {
                let cellValue = cell[0];
                if (
                  player.tetromino &&
                  y >= player.pos.y && y < player.pos.y + player.tetromino.length &&
                  x >= player.pos.x && x < player.pos.x + player.tetromino[0].length
                ) {
                  const pValue = player.tetromino[y - player.pos.y][x - player.pos.x];
                  if (pValue !== 0) cellValue = pValue;
                }
                return (
                  <div
                    key={`${y}-${x}`}
                    className={`tetris-cell ${clearingRows.includes(y) ? 'line-break-anim' : ''}`}
                    style={{ backgroundColor: TETROMINOS[cellValue] ? TETROMINOS[cellValue].color : 'transparent' }}
                  />
                );
              }))}
            </div>
            {gameState === 'paused' && (
              <div className="tetris-pause-overlay">PAUSED</div>
            )}
          </div>

          {/* Sidebar */}
          <div className="tetris-sidebar">
            <div className="tetris-sidebar-block">
              <h3>NEXT</h3>
              <div className="tetris-next-board">
                {/* 4x4 rendering of next piece */}
                {Array.from(Array(4), () => new Array(4).fill(0)).map((row, y) =>
                  row.map((cell, x) => {
                    const blockValue = nextPiece.shape[y] && nextPiece.shape[y][x] ? nextPiece.shape[y][x] : 0;
                    return (
                      <div
                        key={`next-${y}-${x}`}
                        className="tetris-cell"
                        style={{ backgroundColor: TETROMINOS[blockValue] ? TETROMINOS[blockValue].color : 'transparent', border: blockValue !== 0 ? '1px solid rgba(235, 220, 178, 0.2)' : 'none' }}
                      />
                    );
                  })
                )}
              </div>
            </div>

            <div className="tetris-sidebar-block">
              <h3>SCORE</h3>
              <div className="tetris-sidebar-box">{score}</div>
            </div>

            <div className="tetris-sidebar-block">
              <h3>LINES</h3>
              <div className="tetris-sidebar-box">{lines}</div>
            </div>

            <div style={{ marginTop: 'auto' }}>
              <button className="tetris-action-btn" onClick={togglePause}>
                {gameState === 'paused' ? 'RESUME' : 'PAUSE'}
              </button>
              <button className="tetris-action-btn" onClick={quitGame}>QUIT</button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
