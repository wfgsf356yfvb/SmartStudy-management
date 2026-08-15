// ============================================
// PlaySchool Games - 4 Fun Mini Games! (Rewritten Engine)
// ============================================

const GAMES = {
    colorMatch: {
        name: 'Color Match',
        title: '🎨 Color Match!',
        colors: [
            {name:'Red',    emoji:'🔴', hex:'#EF4444'},
            {name:'Blue',   emoji:'🔵', hex:'#3B82F6'},
            {name:'Green',  emoji:'🟢', hex:'#10B981'},
            {name:'Yellow', emoji:'🟡', hex:'#F59E0B'},
            {name:'Purple', emoji:'🟣', hex:'#7C3AED'},
            {name:'Orange', emoji:'🟠', hex:'#FF6B35'},
            {name:'Pink',   emoji:'🌸', hex:'#EC4899'},
            {name:'Cyan',   emoji:'🌊', hex:'#06B6D4'}
        ]
    },
    countAnimals: {
        name: 'Count Animals',
        title: '🐾 Count Animals!',
        animals: ['🐶','🐱','🐸','🐦','🐠','🐘','🦊','🐧','🐻','🦁','🐼','🐨']
    },
    abcFun: {
        name: 'ABC Fun',
        title: '🔤 ABC Fun!',
        letters: 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('')
    },
    shapeSorter: {
        name: 'Shape Sorter',
        title: '🔷 Shape Sorter!',
        shapes: [
            {name:'Circle',   emoji:'⭕'},
            {name:'Square',   emoji:'🟦'},
            {name:'Triangle', emoji:'🔺'},
            {name:'Star',     emoji:'⭐'},
            {name:'Heart',    emoji:'❤️'},
            {name:'Diamond',  emoji:'♦️'}
        ]
    },
    fruitMath: {
        name: 'Fruit Math',
        title: '🍎 Fruit Math!',
        fruits: ['🍎','🍌','🍊','🍓','🍇','🍐','🍉','🍒']
    },
    patternLogic: {
        name: 'Pattern Logic',
        title: '🔁 Pattern Logic!',
        colors: ['🔴','🔵','🟢','🟡','🟣','🟠']
    },
    bigSmall: {
        name: 'Big vs Small',
        title: '🐘 Big vs Small!',
        animals: ['🐭','🐱','🐶','🐮','🦁','🐘','🦖','🐳']
    },
    oddOneOut: {
        name: 'Odd One Out',
        title: '❓ Odd One Out!',
        groups: [
            {name: 'Fruits', items: ['🍎','🍌','🍓','🍇','🍉'], odd: ['🚗','🐶','✏️']},
            {name: 'Animals', items: ['🐶','🦁','🦒','🐘','🦊'], odd: ['🍊','✈️','🍔']},
            {name: 'Space', items: ['🚀','🪐','⭐','🌍','🌙'], odd: ['🍕','🐱','🚲']},
            {name: 'Vehicles', items: ['🚗','🚕','🚌','🚓','🚒'], odd: ['🦆','🍎','⚽']},
            {name: 'Weather', items: ['☀️','🌧️','⚡','❄️','☁️'], odd: ['🍔','🚗','🐶']}
        ]
    },
    vehicleMatch: {
        name: 'Vehicle Match',
        title: '🚗 Vehicle Match!',
        vehicles: [
            {name:'Car', emoji:'🚗'}, {name:'Bus', emoji:'🚌'},
            {name:'Airplane', emoji:'✈️'}, {name:'Train', emoji:'🚂'},
            {name:'Ship', emoji:'🚢'}, {name:'Bike', emoji:'🚲'},
            {name:'Helicopter', emoji:'🚁'}, {name:'Rocket', emoji:'🚀'}
        ]
    },
    planetTrivia: {
        name: 'Planet Blast',
        title: '🌌 Planet Blast!',
        items: ['🌍','🌕','☀️','🚀','🪐','🌟','☄️','🛰️','👽','🛸']
    }
};

let gameState = {
    gameKey: null,
    level: 1,
    maxLevel: 5,
    lives: 3,
    score: 0,
    stars: 0,
    combo: 0,
    timer: null,
    timeLeft: 0,
    maxTime: 0,
    inTransition: false
};

function getStudentClass() {
    return (window.STUDENT_CLASS || 'lkg').toLowerCase();
}

function getBaseTime() {
    const cls = getStudentClass();
    if (cls === 'nursery') return 15;
    if (cls === 'ukg') return 10;
    return 12; // lkg
}

function getOptionsCount(level) {
    if (level === 1) return 2;
    if (level === 2) return 3;
    if (level === 3) return 4;
    if (level === 4) return 5;
    return 6;
}

function openGame(gameKey) {
    gameState = {
        gameKey: gameKey,
        level: 1,
        maxLevel: 5,
        lives: 3,
        score: 0,
        stars: 0,
        combo: 0,
        timer: null,
        timeLeft: 0,
        maxTime: 0,
        inTransition: false
    };
    
    const modal   = document.getElementById('gameModal');
    const title   = document.getElementById('modalTitle');
    const gameArea= document.getElementById('gameArea');
    const result  = document.getElementById('gameResult');
    
    modal.classList.add('open');
    title.textContent = GAMES[gameKey].title;
    result.style.display = 'none';
    gameArea.style.display = 'block';
    
    startGameRound();
}

function closeGame() {
    const modal = document.getElementById('gameModal');
    modal.classList.remove('open');
    stopTimer();
    gameState.gameKey = null;
}

function playAgain() {
    if (!gameState.gameKey) return;
    openGame(gameState.gameKey);
}

function startTimer() {
    stopTimer();
    updateTimerBar();
    
    gameState.timer = setInterval(() => {
        if (gameState.inTransition) return;
        
        gameState.timeLeft--;
        updateTimerBar();
        
        if (gameState.timeLeft <= 0) {
            stopTimer();
            handleTimeOut();
        }
    }, 1000);
}

function stopTimer() {
    if (gameState.timer) {
        clearInterval(gameState.timer);
        gameState.timer = null;
    }
}

function updateTimerBar() {
    const bar = document.getElementById('gameTimerBar');
    if (!bar) return;
    
    const pct = (gameState.timeLeft / gameState.maxTime) * 100;
    bar.style.width = \`\${pct}%\`;
    
    if (pct < 30) {
        bar.style.backgroundColor = '#EF4444'; // Red
    } else if (pct < 60) {
        bar.style.backgroundColor = '#F59E0B'; // Yellow
    } else {
        bar.style.backgroundColor = '#10B981'; // Green
    }
}

function handleTimeOut() {
    gameState.inTransition = true;
    playSound('wrong');
    gameState.lives--;
    gameState.combo = 0;
    
    const gameArea = document.getElementById('gameArea');
    gameArea.style.opacity = '0.5';
    
    setTimeout(() => {
        gameArea.style.opacity = '1';
        if (gameState.lives <= 0) {
            showResult();
        } else {
            startGameRound();
        }
    }, 1500);
}

function startGameRound() {
    if (!gameState.gameKey) return;
    
    if (gameState.lives <= 0 || gameState.level > gameState.maxLevel) {
        showResult();
        return;
    }
    
    gameState.inTransition = false;
    
    let baseTime = getBaseTime();
    gameState.maxTime = Math.max(5, baseTime - (gameState.level - 1));
    gameState.timeLeft = gameState.maxTime;
    
    const gameArea = document.getElementById('gameArea');
    const hearts = '❤️'.repeat(gameState.lives) + '🖤'.repeat(3 - gameState.lives);
    
    const progress = \`
        <div class="game-header-top" style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 10px;">
            <div class="game-level" style="font-weight:bold; font-size:16px;">Level \${gameState.level}/\${gameState.maxLevel}</div>
            <div class="game-lives" style="font-size:16px;">\${hearts}</div>
            <div class="game-score" style="font-weight:bold; font-size:16px;">⭐ \${gameState.score}</div>
        </div>
        <div class="game-timer-container" style="width: 100%; background: #e0e0e0; height: 10px; border-radius: 5px; margin-bottom: 15px; overflow:hidden;">
            <div id="gameTimerBar" style="width: 100%; height: 100%; background: #10B981; transition: width 1s linear, background-color 0.3s;"></div>
        </div>
    \`;

    if (gameState.gameKey === 'colorMatch') renderColorMatch(gameArea, progress);
    else if (gameState.gameKey === 'countAnimals') renderCountAnimals(gameArea, progress);
    else if (gameState.gameKey === 'abcFun') renderAbcFun(gameArea, progress);
    else if (gameState.gameKey === 'shapeSorter') renderShapeSorter(gameArea, progress);
    else if (gameState.gameKey === 'fruitMath') renderFruitMath(gameArea, progress);
    else if (gameState.gameKey === 'patternLogic') renderPatternLogic(gameArea, progress);
    else if (gameState.gameKey === 'bigSmall') renderBigSmall(gameArea, progress);
    else if (gameState.gameKey === 'oddOneOut') renderOddOneOut(gameArea, progress);
    else if (gameState.gameKey === 'vehicleMatch') renderVehicleMatch(gameArea, progress);
    else if (gameState.gameKey === 'planetTrivia') renderPlanetTrivia(gameArea, progress);
    
    startTimer();
}

// ─── COLOR MATCH ─────────────────────────────
function renderColorMatch(gameArea, progress) {
    const colors = GAMES.colorMatch.colors;
    const correct = colors[Math.floor(Math.random() * colors.length)];
    const optionsCount = getOptionsCount(gameState.level);
    const choices = shuffle([correct, ...getRandomFrom(colors.filter(c => c.name !== correct.name), optionsCount - 1)]);

    const cls = getStudentClass();
    const btnSize = cls === 'nursery' ? '100px' : '80px';
    const fontSize = cls === 'nursery' ? '46px' : '36px';

    gameArea.innerHTML = \`
        \${progress}
        <div class="game-question">
            <div class="game-q-text">Tap the <strong style="color:\${correct.hex}">\${correct.name}</strong> colour!</div>
            <div class="color-target" style="background:\${correct.hex};box-shadow:0 0 40px \${correct.hex}66">&nbsp;</div>
        </div>
        <div class="game-choices color-choices">
            \${choices.map(c => \`
                <button class="color-btn" style="background:\${c.hex}; width:\${btnSize}; height:\${btnSize}; font-size:\${fontSize}" 
                    onclick="checkAnswer(this, '\${c.name}', '\${correct.name}')">
                    \${c.emoji}
                </button>
            \`).join('')}
        </div>
    \`;
}

// ─── COUNT ANIMALS ─────────────────────────────
function renderCountAnimals(gameArea, progress) {
    const animals = GAMES.countAnimals.animals;
    const animal  = animals[Math.floor(Math.random() * animals.length)];
    
    let maxCount = 3 + gameState.level * 2; 
    const cls = getStudentClass();
    if (cls === 'ukg') maxCount += 2;
    
    const count = Math.floor(Math.random() * (maxCount - 1)) + 2; 
    
    let wrongOptions = new Set();
    while(wrongOptions.size < getOptionsCount(gameState.level) - 1) {
        let w = count + Math.floor(Math.random() * 5) - 2;
        if (w > 0 && w !== count) wrongOptions.add(w);
    }
    const choices = shuffle([count, ...Array.from(wrongOptions)]);
    const animalRow = Array(count).fill(animal).join(' ');
    const btnSize = cls === 'nursery' ? '80px' : '72px';

    gameArea.innerHTML = \`
        \${progress}
        <div class="game-question">
            <div class="game-q-text">How many animals are there? 🐾</div>
            <div class="animal-display">\${animalRow}</div>
        </div>
        <div class="game-choices number-choices">
            \${choices.map(n => \`
                <button class="number-btn" style="width:\${btnSize}; height:\${btnSize};" onclick="checkAnswer(this, '\${n}', '\${count}')">
                    \${n}
                </button>
            \`).join('')}
        </div>
    \`;
}

// ─── ABC FUN ─────────────────────────────
function renderAbcFun(gameArea, progress) {
    const letters = GAMES.abcFun.letters;
    const cls = getStudentClass();
    const maxIdx = cls === 'nursery' ? 15 : 25;
    
    const correct = letters[Math.floor(Math.random() * maxIdx)]; 
    const optionsCount = getOptionsCount(gameState.level);
    const wrong = shuffle(letters.filter(l => l !== correct)).slice(0, optionsCount - 1);
    const choices = shuffle([correct, ...wrong]);

    const emojis = { A:'🍎', B:'🍌', C:'🐱', D:'🐶', E:'🐘', F:'🐸', G:'🍇', H:'🏠',
                     I:'🍦', J:'🃏', K:'🔑', L:'🦁', M:'🐭', N:'🔤', O:'🍊', P:'🐧',
                     Q:'👸', R:'🌹', S:'⭐', T:'🌲', U:'☂️', V:'🎻', W:'🍉', X:'✖️', Y:'🧶', Z:'🦓' };
    const em = emojis[correct] || '🔤';
    const displaySize = cls === 'nursery' ? '120px' : '100px';

    gameArea.innerHTML = \`
        \${progress}
        <div class="game-question">
            <div class="game-q-text">Which letter is this? \${em}</div>
            <div class="letter-display" style="font-size:\${displaySize}">\${correct}</div>
        </div>
        <div class="game-choices letter-choices">
            \${choices.map(l => \`
                <button class="letter-btn" onclick="checkAnswer(this, '\${l}', '\${correct}')">
                    \${l}
                </button>
            \`).join('')}
        </div>
    \`;
}

// ─── SHAPE SORTER ─────────────────────────────
function renderShapeSorter(gameArea, progress) {
    const shapes = GAMES.shapeSorter.shapes;
    const correct = shapes[Math.floor(Math.random() * shapes.length)];
    const optionsCount = Math.min(getOptionsCount(gameState.level), shapes.length);
    const wrong = shuffle(shapes.filter(s => s.name !== correct.name)).slice(0, optionsCount - 1);
    const choices = shuffle([correct, ...wrong]);

    const cls = getStudentClass();
    const shapeSize = cls === 'nursery' ? '100px' : '80px';

    gameArea.innerHTML = \`
        \${progress}
        <div class="game-question">
            <div class="game-q-text">Find the <strong>\${correct.name}</strong>!</div>
            <div class="shape-display" style="font-size:\${shapeSize}">\${correct.emoji}</div>
        </div>
        <div class="game-choices shape-choices">
            \${choices.map(s => \`
                <button class="shape-btn" onclick="checkAnswer(this, '\${s.name}', '\${correct.name}')">
                    <div class="shape-emoji">\${s.emoji}</div>
                    <div class="shape-name">\${s.name}</div>
                </button>
            \`).join('')}
        </div>
    \`;
}

// ─── FRUIT MATH ─────────────────────────────
function renderFruitMath(gameArea, progress) {
    const fruits = GAMES.fruitMath.fruits;
    const fruit = fruits[Math.floor(Math.random() * fruits.length)];
    
    let maxNum = gameState.level + 2;
    const cls = getStudentClass();
    if (cls === 'ukg') maxNum += 3;
    
    const num1 = Math.floor(Math.random() * maxNum) + 1;
    const num2 = Math.floor(Math.random() * maxNum) + 1;
    const ans = num1 + num2;
    
    const optionsCount = getOptionsCount(gameState.level);
    let wrong = new Set();
    while(wrong.size < optionsCount - 1) {
        let w = ans + Math.floor(Math.random()*6) - 3;
        if (w > 0 && w !== ans) wrong.add(w);
    }
    
    const choices = shuffle([ans, ...Array.from(wrong)]);

    gameArea.innerHTML = \`
        \${progress}
        <div class="game-question">
            <div class="game-q-text">Add the Fruits!</div>
            <div class="math-visual" style="font-size: 32px; background: #FFF5F5; padding: 16px; border-radius: 12px; letter-spacing: 3px;">
                \${fruit.repeat(num1)} <span style="color:#888">+</span> \${fruit.repeat(num2)}
            </div>
        </div>
        <div class="game-choices number-choices">
            \${choices.map(n => \`<button class="number-btn" onclick="checkAnswer(this, '\${n}', '\${ans}')">\${n}</button>\`).join('')}
        </div>
    \`;
}

// ─── PATTERN LOGIC ─────────────────────────────
function renderPatternLogic(gameArea, progress) {
    const c = GAMES.patternLogic.colors;
    const col1 = c[Math.floor(Math.random()*c.length)];
    let col2 = c[Math.floor(Math.random()*c.length)];
    while(col2===col1) col2 = c[Math.floor(Math.random()*c.length)];
    
    let pattern = [col1, col2, col1, col2];
    let ans = col1;
    
    if (gameState.level >= 3) {
        let col3 = c[Math.floor(Math.random()*c.length)];
        while(col3===col1 || col3===col2) col3 = c[Math.floor(Math.random()*c.length)];
        pattern = [col1, col2, col3, col1, col2];
        ans = col3;
    }
    
    const optionsCount = getOptionsCount(gameState.level);
    let wrong = shuffle(c.filter(x => x !== ans)).slice(0, optionsCount - 1);
    const choices = shuffle([ans, ...wrong]);
    
    gameArea.innerHTML = \`
        \${progress}
        <div class="game-question">
            <div class="game-q-text">Complete the pattern! What is next?</div>
            <div class="pattern-line" style="font-size: 38px; margin: 10px 0;">\${pattern.join(' ')} <span style="border:2px dashed #aaa; border-radius:50%; padding:4px 10px; background:#f4f4f4;">?</span></div>
        </div>
        <div class="game-choices color-choices">
            \${choices.map(item => \`<button class="color-btn" style="background:#fff" onclick="checkAnswer(this, '\${item}', '\${ans}')">\${item}</button>\`).join('')}
        </div>
    \`;
}

// ─── BIG vs SMALL ─────────────────────────────
function renderBigSmall(gameArea, progress) {
    const a = GAMES.bigSmall.animals;
    const idx1 = Math.floor(Math.random()*a.length);
    let idx2 = Math.floor(Math.random()*a.length);
    while(idx2===idx1) idx2 = Math.floor(Math.random()*a.length);
    
    const optionsCount = Math.min(3, getOptionsCount(gameState.level));
    let currentChoices = [a[idx1], a[idx2]];
    let ans = idx1 > idx2 ? a[idx1] : a[idx2];
    let questionText = "Which one is BIGGER in the wild?";
    
    if (optionsCount === 3) {
        let idx3 = Math.floor(Math.random()*a.length);
        while(idx3===idx1 || idx3===idx2) idx3 = Math.floor(Math.random()*a.length);
        currentChoices.push(a[idx3]);
        let maxIdx = Math.max(idx1, idx2, idx3);
        let minIdx = Math.min(idx1, idx2, idx3);
        
        if (Math.random() > 0.5) {
            ans = a[maxIdx];
            questionText = "Which one is BIGGEST in the wild?";
        } else {
            ans = a[minIdx];
            questionText = "Which one is SMALLEST in the wild?";
        }
    } else {
        if (Math.random() > 0.5) {
            ans = idx1 < idx2 ? a[idx1] : a[idx2];
            questionText = "Which one is SMALLER in the wild?";
        }
    }
    
    const choices = shuffle(currentChoices);
    
    gameArea.innerHTML = \`
        \${progress}
        <div class="game-question">
            <div class="game-q-text">\${questionText}</div>
        </div>
        <div class="game-choices shape-choices" style="display:flex; justify-content:center; gap: 20px;">
            \${choices.map(item => \`<button class="shape-btn" onclick="checkAnswer(this, '\${item}', '\${ans}')" style="padding:30px;"><div style="font-size:60px">\${item}</div></button>\`).join('')}
        </div>
    \`;
}

// ─── ODD ONE OUT ─────────────────────────────
function renderOddOneOut(gameArea, progress) {
    const grps = GAMES.oddOneOut.groups;
    const grp = grps[Math.floor(Math.random()*grps.length)];
    
    const optionsCount = getOptionsCount(gameState.level);
    const correctItems = shuffle(grp.items).slice(0, optionsCount - 1);
    const oddItem = grp.odd[Math.floor(Math.random()*grp.odd.length)];
    
    const choices = shuffle([...correctItems, oddItem]);

    gameArea.innerHTML = \`
        \${progress}
        <div class="game-question">
            <div class="game-q-text">Find the <strong>Odd One Out</strong>! (Not like others)</div>
        </div>
        <div class="game-choices color-choices">
            \${choices.map(i => \`<button class="color-btn" style="background:#fff; font-size:40px;" onclick="checkAnswer(this, '\${i}', '\${oddItem}')">\${i}</button>\`).join('')}
        </div>
    \`;
}

// ─── VEHICLE MATCH ─────────────────────────────
function renderVehicleMatch(gameArea, progress) {
    const vehicles = GAMES.vehicleMatch.vehicles;
    const correct = vehicles[Math.floor(Math.random()*vehicles.length)];
    const optionsCount = Math.min(getOptionsCount(gameState.level), vehicles.length);
    const choices = shuffle([correct, ...getRandomFrom(vehicles.filter(v=>v.name!==correct.name), optionsCount - 1)]);

    gameArea.innerHTML = \`
        \${progress}
        <div class="game-question">
            <div class="game-q-text">Where is the <strong style="color:var(--primary)">\${correct.name}</strong>?</div>
        </div>
        <div class="game-choices color-choices">
            \${choices.map(v => \`<button class="color-btn" style="background:#fff; font-size:44px;" onclick="checkAnswer(this, '\${v.name}', '\${correct.name}')">\${v.emoji}</button>\`).join('')}
        </div>
    \`;
}

// ─── PLANET TRIVIA ─────────────────────────────
function renderPlanetTrivia(gameArea, progress) {
    const items = GAMES.planetTrivia.items;
    const target = items[Math.floor(Math.random()*items.length)];
    const optionsCount = Math.min(getOptionsCount(gameState.level), items.length);
    const choices = shuffle([target, ...getRandomFrom(items.filter(i=>i!==target), optionsCount - 1)]);
    
    gameArea.innerHTML = \`
        \${progress}
        <div class="game-question">
            <div class="game-q-text">Match the Cosmic Object!</div>
            <div style="font-size: 65px; margin: 15px auto;">\${target}</div>
        </div>
        <div class="game-choices color-choices">
            \${choices.map(i => \`<button class="color-btn" style="background:#fff; font-size:40px;" onclick="checkAnswer(this, '\${i}', '\${target}')">\${i}</button>\`).join('')}
        </div>
    \`;
}

// ─── CHECK ANSWER ─────────────────────────────
function checkAnswer(btn, selected, correct) {
    if (gameState.inTransition) return;
    gameState.inTransition = true;
    stopTimer();

    const allBtns = btn.parentElement.querySelectorAll('button');
    allBtns.forEach(b => b.disabled = true);

    if (selected === correct) {
        btn.classList.add('correct-ans');
        
        gameState.combo++;
        let points = 10 + (gameState.combo >= 3 ? 5 : 0);
        gameState.score += points;
        
        if (gameState.combo >= 3) {
            gameState.stars += 1;
            const comboEl = document.createElement('div');
            comboEl.className = 'combo-text';
            comboEl.textContent = 'Combo +1 ⭐!';
            document.getElementById('gameArea').appendChild(comboEl);
        }
        
        btn.innerHTML += ' ✅';
        playSound('correct');
        
        gameState.level++;
        
        setTimeout(() => {
            if (gameState.level > gameState.maxLevel) {
                showResult();
            } else {
                showLevelCelebration(() => {
                    startGameRound();
                });
            }
        }, 1100);
    } else {
        btn.classList.add('wrong-ans');
        btn.innerHTML += ' ❌';
        gameState.lives--;
        gameState.combo = 0;
        
        allBtns.forEach(b => {
            if (b.onclick && (b.onclick.toString().includes(\`'\${correct}'\`) || b.onclick.toString().includes(\`"\${correct}"\`))) {
                b.classList.add('correct-ans');
            }
        });
        playSound('wrong');
        
        setTimeout(() => {
            if (gameState.lives <= 0) {
                showResult();
            } else {
                startGameRound();
            }
        }, 1500);
    }
}

function showLevelCelebration(callback) {
    const gameArea = document.getElementById('gameArea');
    gameArea.innerHTML = \`
        <div style="text-align:center; padding: 40px 20px;">
            <div style="font-size: 60px; animation: bounce 1s infinite;">🎉</div>
            <h2 style="color: #10B981; font-size: 28px; margin: 20px 0;">Level \${gameState.level - 1} Complete!</h2>
            <p style="font-size: 18px; color: #6B7280;">Get ready for Level \${gameState.level}...</p>
        </div>
    \`;
    setTimeout(callback, 2000);
}

// ─── SHOW RESULT ─────────────────────────────
function showResult() {
    stopTimer();
    
    let win = gameState.level > gameState.maxLevel;
    let baseStars = win ? 3 : (gameState.level >= 4 ? 2 : (gameState.level >= 2 ? 1 : 0));
    let finalStars = Math.min(3, baseStars + gameState.stars); 
    
    let emoji = finalStars >= 3 ? '🏆' : finalStars === 2 ? '🌟' : finalStars === 1 ? '😊' : '😢';
    let title = win ? 'Amazing! You beat all levels!' : (finalStars > 0 ? 'Good Job! You tried hard!' : 'Keep Trying! You Can Do It!');
    let starsHtml = '⭐'.repeat(finalStars) + '☆'.repeat(3 - finalStars);
    if (finalStars > 3) starsHtml = '⭐'.repeat(finalStars);

    document.getElementById('gameArea').style.display   = 'none';
    document.getElementById('gameResult').style.display = 'flex';
    document.getElementById('resultEmoji').textContent  = emoji;
    document.getElementById('resultTitle').textContent  = title;
    document.getElementById('resultStars').textContent  = starsHtml;
    document.getElementById('resultScore').textContent  = \`Score: \${gameState.score} | Reached Level \${Math.min(gameState.level, gameState.maxLevel)}\`;

    const gameName = GAMES[gameState.gameKey]?.name || gameState.gameKey;
    fetch('/student/game/score', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ game_name: gameName, score: gameState.score, stars: finalStars, level: Math.min(gameState.level, gameState.maxLevel) })
    }).catch(() => {});
}

// ─── UTILS ─────────────────────────────
function shuffle(arr) {
    const a = [...arr];
    for (let i = a.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [a[i], a[j]] = [a[j], a[i]];
    }
    return a;
}

function getRandomFrom(arr, n) {
    return shuffle(arr).slice(0, n);
}

function playSound(type) {
    try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);
        if (type === 'correct') {
            osc.frequency.setValueAtTime(523, ctx.currentTime);
            osc.frequency.setValueAtTime(659, ctx.currentTime + 0.1);
            osc.frequency.setValueAtTime(784, ctx.currentTime + 0.2);
        } else {
            osc.frequency.setValueAtTime(300, ctx.currentTime);
            osc.frequency.setValueAtTime(200, ctx.currentTime + 0.15);
        }
        gain.gain.setValueAtTime(0.3, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.4);
        osc.start(ctx.currentTime);
        osc.stop(ctx.currentTime + 0.4);
    } catch(e) {}
}

// Add game styles dynamically
document.addEventListener('DOMContentLoaded', () => {
    const style = document.createElement('style');
    style.textContent = \`
        .combo-text {
            position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
            font-size: 30px; font-weight: bold; color: #F59E0B;
            text-shadow: 2px 2px 0 #fff, -2px -2px 0 #fff, 2px -2px 0 #fff, -2px 2px 0 #fff;
            z-index: 100; animation: popOut 1s forwards; pointer-events: none;
        }
        @keyframes popOut {
            0% { transform: translate(-50%, -50%) scale(0.5); opacity: 0; }
            50% { transform: translate(-50%, -50%) scale(1.2); opacity: 1; }
            100% { transform: translate(-50%, -100%) scale(1); opacity: 0; }
        }
        @keyframes bounce {
            0%, 100% { transform: translateY(0); }
            50% { transform: translateY(-20px); }
        }

        .game-progress { 
            text-align:center; font-weight:700; color:#6B6280; 
            margin-bottom:16px; font-size:14px;
        }
        .game-question { text-align:center; margin-bottom:24px; }
        .game-q-text   { font-size:18px; font-weight:700; margin-bottom:16px; }
        
        .color-target  { 
            width:100px; height:100px; border-radius:50%; 
            margin:0 auto; border:4px solid #fff;
            box-shadow: 0 8px 30px rgba(0,0,0,0.2);
        }
        .color-choices { display:flex; gap:14px; justify-content:center; flex-wrap:wrap; }
        .color-btn { 
            width:80px; height:80px; border-radius:50%; border:4px solid #fff; 
            cursor:pointer; font-size:36px;
            box-shadow:0 4px 15px rgba(0,0,0,0.2);
            transition:transform .15s; display: flex; justify-content: center; align-items: center;
        }
        .color-btn:hover { transform:scale(1.15); }
        
        .animal-display { 
            font-size:36px; line-height:1.4; letter-spacing:2px;
            background:#FFF8F3; border-radius:14px; padding:16px;
            margin-bottom:8px; word-break:break-all;
        }
        .number-choices { display:flex; gap:14px; justify-content:center; flex-wrap:wrap; }
        .number-btn { 
            width:72px; height:72px; border-radius:50%;
            background:linear-gradient(135deg,#7C3AED,#A78BFA);
            border:none; color:#fff; font-size:28px; font-weight:900;
            cursor:pointer; transition:transform .15s;
            font-family:'Baloo 2',cursive; display: flex; justify-content: center; align-items: center;
        }
        .number-btn:hover { transform:scale(1.12); }
        
        .letter-display { 
            font-family:'Baloo 2',cursive; font-weight:900;
            color:#FF6B35; line-height:1; margin-bottom:8px;
            text-shadow:0 4px 20px rgba(255,107,53,0.3);
        }
        .letter-choices { display:flex; gap:14px; justify-content:center; flex-wrap:wrap; }
        .letter-btn { 
            width:72px; height:72px; border-radius:16px;
            background:linear-gradient(135deg,#FF6B35,#FF8C5A);
            border:none; color:#fff; font-size:30px; font-weight:900;
            cursor:pointer; transition:transform .15s;
            font-family:'Baloo 2',cursive; display: flex; justify-content: center; align-items: center;
        }
        .letter-btn:hover { transform:scale(1.12); }
        
        .shape-display { font-size:80px; margin-bottom:8px; }
        .shape-choices { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
        .shape-btn { 
            padding:16px; border-radius:16px; border:3px solid #F0E8E0;
            background:#fff; cursor:pointer; transition:all .15s;
            display:flex; flex-direction:column; align-items:center; gap:6px;
        }
        .shape-btn:hover { border-color:#7C3AED; transform:scale(1.05); }
        .shape-emoji { font-size:42px; }
        .shape-name  { font-weight:700; font-size:14px; }
        
        .correct-ans { 
            border:4px solid #10B981 !important; 
            box-shadow:0 0 20px rgba(16,185,129,0.4) !important;
            transform:scale(1.1) !important;
        }
        .wrong-ans { 
            border:4px solid #EF4444 !important; opacity:.7;
        }
    \`;
    document.head.appendChild(style);
});
