/**
 * Telegram Bot Token Studio — Client Application Controller
 * Handles SSE streaming, Web Audio synthesis, batch validation, token generation, and export.
 */

class TokenStudioApp {
  constructor() {
    // Application State
    this.state = {
      audioEnabled: true,
      maskTokens: true,
      isValidating: false,
      abortController: null,
      stats: {
        total: 0,
        hits: 0,
        misses: 0,
        totalLatency: 0,
      },
      verifiedHits: [],
      allProcessedResults: [],
    };

    // Audio Context (Web Audio API for lightweight synthetic audio feedback)
    this.audioCtx = null;

    // DOM Elements
    this.dom = {
      // Nav & Toggles
      soundToggleBtn: document.getElementById('sound-toggle-btn'),
      soundLabel: document.getElementById('sound-label'),
      maskToggleBtn: document.getElementById('mask-toggle-btn'),
      maskLabel: document.getElementById('mask-label'),
      tabButtons: document.querySelectorAll('.tab-btn'),
      tabContents: document.querySelectorAll('.tab-content'),

      // Stats
      statTotal: document.getElementById('stat-total'),
      statHits: document.getElementById('stat-hits'),
      statMisses: document.getElementById('stat-misses'),
      statLatency: document.getElementById('stat-latency'),
      hitRateBadge: document.getElementById('hit-rate-badge'),
      vaultCountBadge: document.getElementById('vault-count-badge'),

      // Tab 1: Validator
      tokenInput: document.getElementById('token-input-area'),
      tokenCountIndicator: document.getElementById('input-token-count'),
      dropzone: document.getElementById('dropzone'),
      fileInput: document.getElementById('file-upload-input'),
      // Tab 1: Validator
      tokenInput: document.getElementById('token-input-area'),
      tokenCountIndicator: document.getElementById('input-token-count'),
      dropzone: document.getElementById('dropzone'),
      fileInput: document.getElementById('file-upload-input'),
      loadDemoBtn: document.getElementById('load-demo-btn'),
      clearInputBtn: document.getElementById('clear-input-btn'),
      concurrencySlider: document.getElementById('concurrency-slider'),
      concurrencyVal: document.getElementById('concurrency-val'),
      delaySlider: document.getElementById('delay-slider'),
      delayVal: document.getElementById('delay-val'),
      demoCheckbox: document.getElementById('demo-mode-checkbox'),
      enableTgAlert: document.getElementById('enable-tg-alert'),
      tgAlertBotToken: document.getElementById('tg-alert-bot-token'),
      tgAlertChatId: document.getElementById('tg-alert-chat-id'),
      btnTestTgAlert: document.getElementById('btn-test-tg-alert'),
      // Proxy DOM Elements
      enableProxiesToggle: document.getElementById('enable-proxies-toggle'),
      btnAutoFetchProxies: document.getElementById('btn-auto-fetch-proxies'),
      btnTestProxiesHealth: document.getElementById('btn-test-proxies-health'),
      proxyCountStatus: document.getElementById('proxy-count-status'),
      proxyListArea: document.getElementById('proxy-list-area'),
      startBtn: document.getElementById('start-validation-btn'),
      stopBtn: document.getElementById('stop-validation-btn'),
      progressSection: document.getElementById('progress-section'),
      progressBarFill: document.getElementById('progress-bar-fill'),
      progressStatusText: document.getElementById('progress-status-text'),
      progressPercentText: document.getElementById('progress-percent-text'),
      liveFeedList: document.getElementById('live-feed-list'),
      emptyFeedPlaceholder: document.getElementById('empty-feed-placeholder'),
      clearFeedBtn: document.getElementById('clear-feed-btn'),

      // Tab 2: Generator
      genCountInput: document.getElementById('gen-count-input'),
      genDigitsRange: document.getElementById('gen-digits-range'),
      genSecretLen: document.getElementById('gen-secret-len'),
      runGenBtn: document.getElementById('btn-run-generate'),
      genWrapper: document.getElementById('generated-wrapper'),
      genCountLabel: document.getElementById('gen-count-label'),
      genOutputArea: document.getElementById('gen-output-area'),
      copyGenBtn: document.getElementById('btn-copy-gen'),
      downloadGenBtn: document.getElementById('btn-download-gen'),
      sendToValBtn: document.getElementById('btn-send-to-validator'),

      // Tab 3: Vault
      vaultSearchInput: document.getElementById('vault-search-input'),
      vaultTableBody: document.getElementById('vault-table-body'),
      exportJsonBtn: document.getElementById('btn-export-json'),
      exportCsvBtn: document.getElementById('btn-export-csv'),
      clearVaultBtn: document.getElementById('btn-clear-vault'),

      // Tab 4: Terminal
      terminalScreen: document.getElementById('terminal-screen'),
      terminalAutoScroll: document.getElementById('terminal-autoscroll'),
      clearTerminalBtn: document.getElementById('btn-clear-terminal'),

      // Toasts
      toastContainer: document.getElementById('toast-container'),

      // Join Modal
      tgJoinModal: document.getElementById('tg-join-modal'),
      btnCloseModal: document.getElementById('btn-close-modal'),
      btnModalContinue: document.getElementById('btn-modal-continue'),
    };

    this.init();
  }

  init() {
    this.setupEventListeners();
    this.setupModal();
    this.updateTokenInputCount();
    this.logTerminal('System ready. Version 2.0.0 initialized.', 'system');
  }

  // =========================================================================
  // Audio Feedback (Web Audio API)
  // =========================================================================
  playBeep(type = 'click') {
    if (!this.state.audioEnabled) return;
    try {
      if (!this.audioCtx) {
        const AudioCtxClass = window.AudioContext || window.webkitAudioContext;
        if (AudioCtxClass) this.audioCtx = new AudioCtxClass();
      }
      if (this.audioCtx && this.audioCtx.state === 'suspended') {
        this.audioCtx.resume();
      }
      if (!this.audioCtx) return;

      const osc = this.audioCtx.createOscillator();
      const gain = this.audioCtx.createGain();
      osc.connect(gain);
      gain.connect(this.audioCtx.destination);

      const now = this.audioCtx.currentTime;

      if (type === 'hit') {
        // High pleasant dual chime
        osc.type = 'sine';
        osc.frequency.setValueAtTime(587.33, now); // D5
        osc.frequency.exponentialRampToValueAtTime(880.00, now + 0.12); // A5
        gain.gain.setValueAtTime(0.18, now);
        gain.gain.exponentialRampToValueAtTime(0.01, now + 0.25);
        osc.start(now);
        osc.stop(now + 0.25);
      } else if (type === 'skip') {
        // Soft low click
        osc.type = 'triangle';
        osc.frequency.setValueAtTime(220, now);
        osc.frequency.exponentialRampToValueAtTime(110, now + 0.08);
        gain.gain.setValueAtTime(0.08, now);
        gain.gain.exponentialRampToValueAtTime(0.01, now + 0.08);
        osc.start(now);
        osc.stop(now + 0.08);
      } else {
        // Subtle UI click
        osc.type = 'sine';
        osc.frequency.setValueAtTime(800, now);
        gain.gain.setValueAtTime(0.05, now);
        gain.gain.exponentialRampToValueAtTime(0.01, now + 0.04);
        osc.start(now);
        osc.stop(now + 0.04);
      }
    } catch (e) {
      // Audio context error fallback silent
    }
  }

  // =========================================================================
  // Event Listeners
  // =========================================================================
  setupEventListeners() {
    // Tabs Navigation
    this.dom.tabButtons.forEach((btn) => {
      btn.addEventListener('click', () => {
        const targetTab = btn.getAttribute('data-tab');
        this.switchTab(targetTab);
        this.playBeep('click');
      });
    });

    // Sound Toggle
    this.dom.soundToggleBtn.addEventListener('click', () => {
      this.state.audioEnabled = !this.state.audioEnabled;
      this.dom.soundToggleBtn.classList.toggle('active', this.state.audioEnabled);
      this.dom.soundLabel.textContent = this.state.audioEnabled ? 'Audio ON' : 'Audio OFF';
      this.showToast(this.state.audioEnabled ? 'Sound feedback enabled' : 'Sound feedback disabled', 'info');
      if (this.state.audioEnabled) this.playBeep('hit');
    });

    // Mask Toggle
    this.dom.maskToggleBtn.addEventListener('click', () => {
      this.state.maskTokens = !this.state.maskTokens;
      this.dom.maskToggleBtn.classList.toggle('active', this.state.maskTokens);
      this.dom.maskLabel.textContent = this.state.maskTokens ? 'Mask Tokens' : 'Show Tokens';
      this.renderVaultTable();
      this.showToast(this.state.maskTokens ? 'Tokens masked for privacy' : 'Full tokens visible', 'info');
    });

    // Sliders
    this.dom.concurrencySlider.addEventListener('input', (e) => {
      this.dom.concurrencyVal.textContent = e.target.value;
    });
    this.dom.delaySlider.addEventListener('input', (e) => {
      this.dom.delayVal.textContent = `${e.target.value}s`;
    });

    // Input area changes
    this.dom.tokenInput.addEventListener('input', () => this.updateTokenInputCount());

    // Load Demo Tokens Button
    this.dom.loadDemoBtn.addEventListener('click', async () => {
      this.playBeep('click');
      try {
        const res = await fetch('/api/demo-samples');
        const data = await res.json();
        this.dom.tokenInput.value = data.all.join('\n');
        this.dom.demoCheckbox.checked = true;
        this.updateTokenInputCount();
        this.showToast('Demo tokens loaded into matrix', 'info');
      } catch (err) {
        this.showToast('Failed to load demo tokens', 'error');
      }
    });

    // Clear Input Button
    this.dom.clearInputBtn.addEventListener('click', () => {
      this.dom.tokenInput.value = '';
      this.updateTokenInputCount();
      this.playBeep('click');
    });

    // File Upload & Drag-and-drop
    this.dom.fileInput.addEventListener('change', (e) => this.handleFileSelect(e));
    this.setupDragAndDrop();

    // Start / Stop Validation
    this.dom.startBtn.addEventListener('click', () => this.startValidationPipeline());
    this.dom.stopBtn.addEventListener('click', () => this.stopValidationPipeline());

    // Test Telegram Alert Ping Button
    if (this.dom.btnTestTgAlert) {
      this.dom.btnTestTgAlert.addEventListener('click', async () => {
        const botToken = (this.dom.tgAlertBotToken.value || '').trim();
        const chatId = (this.dom.tgAlertChatId.value || '').trim();
        if (!botToken || !chatId) {
          this.showToast('Please enter both Alert Bot Token and Chat ID', 'error');
          return;
        }
        this.dom.btnTestTgAlert.disabled = true;
        this.playBeep('click');
        this.showToast('Sending test ping to Telegram...', 'info');

        try {
          const res = await fetch('/api/test-notify', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ bot_token: botToken, chat_id: chatId }),
          });
          const data = await res.json();
          if (!res.ok) {
            throw new Error(data.detail || 'Failed to send alert');
          }
          this.showToast('✅ Test message sent! Check your Telegram chat.', 'success');
          this.playBeep('hit');
          this.logTerminal(`[NOTIFICATION] Test ping sent successfully to Chat ID: ${chatId}`, 'hit');
        } catch (err) {
          this.showToast(`Error: ${err.message}`, 'error');
          this.logTerminal(`[NOTIFICATION ERROR] ${err.message}`, 'skip');
        } finally {
          this.dom.btnTestTgAlert.disabled = false;
        }
      });
    }

    // Proxy Engine Event Handlers
    if (this.dom.btnAutoFetchProxies) {
      this.dom.btnAutoFetchProxies.addEventListener('click', async () => {
        this.dom.btnAutoFetchProxies.disabled = true;
        this.playBeep('click');
        this.showToast('Fetching latest free live proxies...', 'info');

        try {
          const res = await fetch('/api/fetch-free-proxies', { method: 'POST' });
          const data = await res.json();
          if (!res.ok) throw new Error(data.detail || 'Failed to fetch proxies');

          this.dom.proxyListArea.value = data.proxies.join('\n');
          this.dom.enableProxiesToggle.checked = true;
          this.updateProxyCount();
          this.showToast(`✅ Loaded ${data.count} free public proxies!`, 'success');
          this.playBeep('hit');
          this.logTerminal(`[PROXIES] Auto-fetched ${data.count} free HTTP proxies from open sources.`, 'hit');
        } catch (err) {
          this.showToast(`Proxy fetch error: ${err.message}`, 'error');
          this.logTerminal(`[PROXY ERROR] ${err.message}`, 'skip');
        } finally {
          this.dom.btnAutoFetchProxies.disabled = false;
        }
      });
    }

    if (this.dom.btnTestProxiesHealth) {
      this.dom.btnTestProxiesHealth.addEventListener('click', async () => {
        const rawProxies = this.parseProxyInput();
        if (rawProxies.length === 0) {
          this.showToast('No proxies to test. Enter proxies or click Auto-Fetch.', 'error');
          return;
        }

        this.dom.btnTestProxiesHealth.disabled = true;
        this.playBeep('click');
        this.showToast(`Testing ${Math.min(rawProxies.length, 50)} proxies latency...`, 'info');

        try {
          const res = await fetch('/api/test-proxies', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ proxies: rawProxies, timeout: 3.5 }),
          });
          const data = await res.json();
          if (!res.ok) throw new Error(data.detail || 'Test failed');

          this.showToast(`Tested: ${data.alive_count} Alive / ${data.dead_count} Offline`, data.alive_count > 0 ? 'success' : 'info');
          this.logTerminal(`[PROXY TEST] Checked ${data.total} proxies: ${data.alive_count} live, ${data.dead_count} unresponsive.`, 'info');
          this.playBeep(data.alive_count > 0 ? 'hit' : 'skip');
        } catch (err) {
          this.showToast(`Error testing proxies: ${err.message}`, 'error');
        } finally {
          this.dom.btnTestProxiesHealth.disabled = false;
        }
      });
    }

    if (this.dom.proxyListArea) {
      this.dom.proxyListArea.addEventListener('input', () => this.updateProxyCount());
    }

    // Clear Feed
    this.dom.clearFeedBtn.addEventListener('click', () => {
      this.dom.liveFeedList.innerHTML = '';
      this.dom.liveFeedList.appendChild(this.dom.emptyFeedPlaceholder);
      this.dom.emptyFeedPlaceholder.style.display = 'flex';
      this.playBeep('click');
    });

    // Generator Controls
    this.dom.runGenBtn.addEventListener('click', () => this.generateMockTokens());
    this.dom.copyGenBtn.addEventListener('click', () => {
      this.copyToClipboard(this.dom.genOutputArea.value, 'Generated tokens copied!');
    });
    this.dom.downloadGenBtn.addEventListener('click', () => {
      this.downloadTextFile('generated_tokens.txt', this.dom.genOutputArea.value);
    });
    this.dom.sendToValBtn.addEventListener('click', () => {
      this.dom.tokenInput.value = this.dom.genOutputArea.value;
      this.updateTokenInputCount();
      this.switchTab('tab-validator');
      this.showToast('Tokens transferred to validator matrix', 'success');
      this.playBeep('click');
    });

    // Vault Search & Exports
    this.dom.vaultSearchInput.addEventListener('input', () => this.renderVaultTable());
    this.dom.exportJsonBtn.addEventListener('click', () => this.exportVault('json'));
    this.dom.exportCsvBtn.addEventListener('click', () => this.exportVault('csv'));
    this.dom.clearVaultBtn.addEventListener('click', () => {
      this.state.verifiedHits = [];
      this.renderVaultTable();
      this.updateHUDStats();
      this.showToast('Vault cleared', 'info');
      this.playBeep('click');
    });

    // Terminal Clear
    this.dom.clearTerminalBtn.addEventListener('click', () => {
      this.dom.terminalScreen.innerHTML = '';
      this.logTerminal('Terminal cleared.', 'system');
      this.playBeep('click');
    });
  }

  // =========================================================================
  // Telegram Join Popup Modal
  // =========================================================================
  setupModal() {
    const modal = this.dom.tgJoinModal;
    if (!modal) return;

    const closeModal = () => {
      modal.classList.add('closing');
      setTimeout(() => {
        modal.style.display = 'none';
        modal.classList.remove('closing');
      }, 250);
      this.playBeep('click');
    };

    if (this.dom.btnCloseModal) {
      this.dom.btnCloseModal.addEventListener('click', closeModal);
    }

    if (this.dom.btnModalContinue) {
      this.dom.btnModalContinue.addEventListener('click', closeModal);
    }

    modal.addEventListener('click', (e) => {
      if (e.target === modal) {
        closeModal();
      }
    });
  }

  // =========================================================================
  // Drag & Drop
  // =========================================================================
  setupDragAndDrop() {
    const dropzone = this.dom.dropzone;
    ['dragenter', 'dragover'].forEach((eventName) => {
      dropzone.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropzone.classList.add('dragover');
      });
    });

    ['dragleave', 'drop'].forEach((eventName) => {
      dropzone.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropzone.classList.remove('dragover');
      });
    });

    dropzone.addEventListener('drop', (e) => {
      const dt = e.dataTransfer;
      const files = dt.files;
      if (files.length > 0) {
        this.readFile(files[0]);
      }
    });
  }

  handleFileSelect(e) {
    const file = e.target.files[0];
    if (file) {
      this.readFile(file);
    }
  }

  readFile(file) {
    const reader = new FileReader();
    reader.onload = (event) => {
      this.dom.tokenInput.value = event.target.result;
      this.updateTokenInputCount();
      this.showToast(`Loaded ${file.name}`, 'success');
      this.playBeep('click');
    };
    reader.readAsText(file);
  }

  // =========================================================================
  // Tab Switching
  // =========================================================================
  switchTab(tabId) {
    this.dom.tabButtons.forEach((btn) => {
      const isTarget = btn.getAttribute('data-tab') === tabId;
      btn.classList.toggle('active', isTarget);
      btn.setAttribute('aria-selected', isTarget ? 'true' : 'false');
    });

    this.dom.tabContents.forEach((content) => {
      content.classList.toggle('active', content.id === tabId);
    });
  }

  // =========================================================================
  // Validation Pipeline (SSE Streaming)
  // =========================================================================
  async startValidationPipeline() {
    const rawTokens = this.parseTokenInput();
    if (rawTokens.length === 0) {
      this.showToast('Please enter at least one token to validate', 'error');
      return;
    }

    this.state.isValidating = true;
    this.dom.startBtn.disabled = true;
    this.dom.stopBtn.disabled = false;
    this.dom.progressSection.style.display = 'block';
    this.dom.emptyFeedPlaceholder.style.display = 'none';

    // Reset progress and HUD
    this.updateProgress(0, rawTokens.length);
    this.logTerminal(`Starting pipeline for ${rawTokens.length} token(s)...`, 'info');

    this.state.abortController = new AbortController();

    const isTgAlertEnabled = this.dom.enableTgAlert ? this.dom.enableTgAlert.checked : false;
    const notifyBotToken = this.dom.tgAlertBotToken ? (this.dom.tgAlertBotToken.value || '').trim() : '';
    const notifyChatId = this.dom.tgAlertChatId ? (this.dom.tgAlertChatId.value || '').trim() : '';

    const isProxiesEnabled = this.dom.enableProxiesToggle ? this.dom.enableProxiesToggle.checked : false;
    const proxyList = this.parseProxyInput();

    const payload = {
      tokens: rawTokens,
      demo_mode: this.dom.demoCheckbox.checked,
      concurrency: parseInt(this.dom.concurrencySlider.value, 10),
      delay: parseFloat(this.dom.delaySlider.value),
      timeout: 8.0,
      max_retries: 1,
      notify_telegram: isTgAlertEnabled,
      notify_bot_token: notifyBotToken,
      notify_chat_id: notifyChatId,
      use_proxies: isProxiesEnabled && proxyList.length > 0,
      proxies: proxyList,
    };



    try {
      const response = await fetch('/api/validate-stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: this.state.abortController.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP Error ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split('\n\n');
        buffer = events.pop(); // Keep incomplete chunk in buffer

        for (const evt of events) {
          if (evt.startsWith('data: ')) {
            const dataStr = evt.replace(/^data: /, '').trim();
            if (dataStr) {
              try {
                const eventData = JSON.parse(dataStr);
                this.handleStreamEvent(eventData);
              } catch (parseErr) {
                console.error('SSE JSON parse error:', parseErr, dataStr);
              }
            }
          }
        }
      }
    } catch (err) {
      if (err.name === 'AbortError') {
        this.logTerminal('Pipeline cancelled by operator.', 'system');
        this.showToast('Validation stopped', 'info');
      } else {
        this.logTerminal(`Pipeline error: ${err.message}`, 'skip');
        this.showToast(`Error: ${err.message}`, 'error');
      }
    } finally {
      this.state.isValidating = false;
      this.dom.startBtn.disabled = false;
      this.dom.stopBtn.disabled = true;
      this.logTerminal('Pipeline execution finished.', 'system');
    }
  }

  stopValidationPipeline() {
    if (this.state.abortController) {
      this.state.abortController.abort();
    }
  }

  handleStreamEvent(event) {
    if (event.type === 'init') {
      this.logTerminal(`Initialized pool: ${event.total} tokens, concurrency=${event.concurrency}, demo=${event.demo_mode}`, 'system');
    } else if (event.type === 'item') {
      const res = event.result;
      this.state.stats.total++;
      this.state.allProcessedResults.push(res);

      if (res.latency_ms) {
        this.state.stats.totalLatency += res.latency_ms;
      }

      if (res.valid) {
        this.state.stats.hits++;
        this.state.verifiedHits.push(res);
        this.playBeep('hit');
        this.addLiveFeedCard(res, true);
        this.renderVaultTable();
        this.logTerminal(`[HIT] @${res.username || 'unnamed'} (ID: ${res.bot_id}) — ${this.mask(res.token)} (${res.latency_ms}ms)`, 'hit');
      } else {
        this.state.stats.misses++;
        this.playBeep('skip');
        this.addLiveFeedCard(res, false);
        this.logTerminal(`[SKIP] ${this.mask(res.token)} — ${res.reason || 'invalid'}`, 'skip');
      }

      this.updateProgress(event.completed, event.total);
      this.updateHUDStats();
    } else if (event.type === 'finish') {
      this.updateHUDStats();
      this.showToast(`Completed! ${event.hits} hits out of ${event.total} checked`, event.hits > 0 ? 'success' : 'info');
    }
  }

  // =========================================================================
  // UI Renderers & Feed
  // =========================================================================
  addLiveFeedCard(res, isHit) {
    const card = document.createElement('div');
    card.className = `feed-card ${isHit ? 'hit' : 'skip'}`;

    const displayToken = this.state.maskTokens ? this.mask(res.token) : res.token;

    if (isHit) {
      const flags = [];
      if (res.can_join_groups) flags.push('groups');
      if (res.can_read_all_group_messages) flags.push('read-all');
      if (res.supports_inline_queries) flags.push('inline');

      card.innerHTML = `
        <div class="feed-card-header">
          <span class="badge-tag hit">&#10003; HIT</span>
          <span class="feed-latency">${res.latency_ms || 20} ms</span>
        </div>
        <div class="feed-bot-title">
          <span>${this.escapeHtml(res.first_name || 'Telegram Bot')}</span>
          <a class="feed-bot-handle" href="https://t.me/${res.username}" target="_blank" rel="noopener">@${res.username}</a>
        </div>
        <div class="feed-token-str">
          <code>${displayToken}</code>
          <span class="token-id-chip">ID: ${res.bot_id || 'N/A'}</span>
        </div>
        ${flags.length > 0 ? `<div class="feed-flags-row">${flags.map(f => `<span class="flag-chip">${f}</span>`).join('')}</div>` : ''}
      `;
    } else {
      card.innerHTML = `
        <div class="feed-card-header">
          <span class="badge-tag skip">&#10007; SKIP</span>
          <span class="feed-latency">${res.latency_ms ? res.latency_ms + ' ms' : '--'}</span>
        </div>
        <div class="feed-token-str">
          <code>${displayToken}</code>
        </div>
        <div class="feed-reason-text">${this.escapeHtml(res.reason || 'unauthorized')}</div>
      `;
    }

    // Insert at top of list
    this.dom.liveFeedList.insertBefore(card, this.dom.liveFeedList.firstChild);

    // Limit feed cards to 100 in DOM for performance
    if (this.dom.liveFeedList.children.length > 100) {
      this.dom.liveFeedList.removeChild(this.dom.liveFeedList.lastChild);
    }
  }

  updateProgress(current, total) {
    const pct = total > 0 ? Math.round((current / total) * 100) : 0;
    this.dom.progressBarFill.style.width = `${pct}%`;
    this.dom.progressStatusText.textContent = `Validating ${current} of ${total}...`;
    this.dom.progressPercentText.textContent = `${pct}%`;
  }

  updateHUDStats() {
    const { total, hits, misses, totalLatency } = this.state.stats;
    this.dom.statTotal.textContent = total;
    this.dom.statHits.textContent = hits;
    this.dom.statMisses.textContent = misses;
    this.dom.vaultCountBadge.textContent = this.state.verifiedHits.length;

    const hitRate = total > 0 ? Math.round((hits / total) * 100) : 0;
    this.dom.hitRateBadge.textContent = `${hitRate}%`;

    const avgLatency = total > 0 ? Math.round(totalLatency / total) : 0;
    this.dom.statLatency.textContent = avgLatency > 0 ? `${avgLatency} ms` : '-- ms';
  }

  // =========================================================================
  // Generator Tab
  // =========================================================================
  async generateMockTokens() {
    const count = parseInt(this.dom.genCountInput.value, 10) || 10;
    const [minDigits, maxDigits] = this.dom.genDigitsRange.value.split(',').map(Number);
    const tokenLength = parseInt(this.dom.genSecretLen.value, 10) || 45;

    this.dom.runGenBtn.disabled = true;
    this.playBeep('click');

    try {
      const res = await fetch('/api/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          count: count,
          bot_id_min_digits: minDigits,
          bot_id_max_digits: maxDigits,
          token_length: tokenLength,
        }),
      });

      const data = await res.json();
      this.dom.genOutputArea.value = data.tokens.join('\n');
      this.dom.genCountLabel.textContent = `Generated ${data.tokens.length} mock token(s)`;
      this.dom.genWrapper.style.display = 'block';
      this.showToast(`Generated ${data.tokens.length} mock tokens`, 'success');
      this.playBeep('hit');
    } catch (err) {
      this.showToast('Generation failed', 'error');
    } finally {
      this.dom.runGenBtn.disabled = false;
    }
  }

  // =========================================================================
  // Vault Data Explorer & Table
  // =========================================================================
  renderVaultTable() {
    const query = (this.dom.vaultSearchInput.value || '').toLowerCase().trim();
    const hits = this.state.verifiedHits.filter((hit) => {
      if (!query) return true;
      return (
        (hit.username && hit.username.toLowerCase().includes(query)) ||
        (hit.first_name && hit.first_name.toLowerCase().includes(query)) ||
        (hit.bot_id && String(hit.bot_id).includes(query)) ||
        (hit.token && hit.token.toLowerCase().includes(query))
      );
    });

    if (hits.length === 0) {
      this.dom.vaultTableBody.innerHTML = `
        <tr class="empty-row">
          <td colspan="7">
            <div class="table-empty-notice">
              <span>${this.state.verifiedHits.length === 0 ? 'No verified bot tokens recorded yet.' : 'No bots matched your search criteria.'}</span>
            </div>
          </td>
        </tr>
      `;
      return;
    }

    this.dom.vaultTableBody.innerHTML = hits.map((hit) => {
      const displayToken = this.state.maskTokens ? this.mask(hit.token) : hit.token;
      const initial = (hit.first_name || hit.username || 'B').charAt(0).toUpperCase();

      const flags = [];
      if (hit.can_join_groups) flags.push('groups');
      if (hit.can_read_all_group_messages) flags.push('read-all');
      if (hit.supports_inline_queries) flags.push('inline');

      return `
        <tr>
          <td>
            <div class="vault-bot-cell">
              <div class="bot-avatar">${initial}</div>
              <div>
                <div class="bot-meta-name">${this.escapeHtml(hit.first_name || 'Bot')}</div>
                <span style="font-size: 0.72rem; color: var(--text-dim);">${hit.checked_at ? hit.checked_at.slice(11, 19) : ''}</span>
              </div>
            </div>
          </td>
          <td><code style="color: #38bdf8;">${hit.bot_id || 'N/A'}</code></td>
          <td>
            <a class="tg-link-pill" href="https://t.me/${hit.username}" target="_blank" rel="noopener">@${hit.username || 'unknown'}</a>
          </td>
          <td>
            <div style="display: flex; gap: 4px; flex-wrap: wrap;">
              ${flags.map(f => `<span class="flag-chip">${f}</span>`).join('')}
            </div>
          </td>
          <td><code>${hit.latency_ms || 20} ms</code></td>
          <td><span class="token-cell-code">${displayToken}</span></td>
          <td>
            <button class="btn btn-xs btn-outline" onclick="window.app.copyToClipboard('${hit.token}', 'Token copied!')" title="Copy full token">
              Copy
            </button>
          </td>
        </tr>
      `;
    }).join('');
  }

  exportVault(format = 'json') {
    if (this.state.verifiedHits.length === 0) {
      this.showToast('Vault is empty. No hits to export.', 'info');
      return;
    }

    const timestamp = new Date().toISOString().slice(0, 19).replace(/:/g, '-');

    if (format === 'json') {
      const dataStr = JSON.stringify(this.state.verifiedHits, null, 2);
      this.downloadTextFile(`telegram_bot_hits_${timestamp}.json`, dataStr, 'application/json');
      this.showToast('Exported JSON successfully', 'success');
    } else if (format === 'csv') {
      const headers = ['token', 'bot_id', 'username', 'first_name', 'can_join_groups', 'can_read_all_group_messages', 'supports_inline_queries', 'latency_ms', 'checked_at'];
      const rows = this.state.verifiedHits.map((h) => headers.map((key) => JSON.stringify(h[key] ?? '')).join(','));
      const csvStr = [headers.join(','), ...rows].join('\n');
      this.downloadTextFile(`telegram_bot_hits_${timestamp}.csv`, csvStr, 'text/csv');
      this.showToast('Exported CSV successfully', 'success');
    }
  }

  // =========================================================================
  // Terminal Logger
  // =========================================================================
  logTerminal(message, type = 'info') {
    const line = document.createElement('div');
    line.className = `term-line ${type}`;
    const time = new Date().toTimeString().slice(0, 8);
    line.textContent = `[${time}] ${message}`;
    this.dom.terminalScreen.appendChild(line);

    if (this.dom.terminalAutoScroll.checked) {
      this.dom.terminalScreen.scrollTop = this.dom.terminalScreen.scrollHeight;
    }
  }

  // =========================================================================
  // Utilities
  // =========================================================================
  parseTokenInput() {
    const raw = this.dom.tokenInput.value;
    return raw
      .split('\n')
      .map((line) => line.trim())
      .filter((line) => line && !line.startsWith('#'));
  }

  updateTokenInputCount() {
    const count = this.parseTokenInput().length;
    this.dom.tokenCountIndicator.textContent = `${count} token${count === 1 ? '' : 's'} detected`;
  }

  parseProxyInput() {
    if (!this.dom.proxyListArea) return [];
    const raw = this.dom.proxyListArea.value || '';
    return raw
      .split('\n')
      .map((line) => line.trim())
      .filter((line) => line && !line.startsWith('#'));
  }

  updateProxyCount() {
    if (!this.dom.proxyCountStatus) return;
    const count = this.parseProxyInput().length;
    this.dom.proxyCountStatus.textContent = `${count} prox${count === 1 ? 'y' : 'ies'} loaded`;
  }


  mask(token) {
    if (!token) return '<empty>';
    if (token.includes(':')) {
      const [id, secret] = token.split(':');
      if (secret.length <= 8) return `${id}:********`;
      return `${id}:${secret.slice(0, 4)}****************${secret.slice(-4)}`;
    }
    return token.length > 8 ? `${token.slice(0, 4)}****${token.slice(-4)}` : '********';
  }

  escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  copyToClipboard(text, successMsg = 'Copied to clipboard!') {
    navigator.clipboard.writeText(text).then(() => {
      this.showToast(successMsg, 'success');
      this.playBeep('click');
    }).catch(() => {
      this.showToast('Failed to copy to clipboard', 'error');
    });
  }

  downloadTextFile(filename, content, type = 'text/plain;charset=utf-8') {
    const blob = new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    this.dom.toastContainer.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateX(100%)';
      toast.style.transition = 'all 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, 3200);
  }
}

// Instantiate and attach globally for inline handlers
document.addEventListener('DOMContentLoaded', () => {
  window.app = new TokenStudioApp();
});
