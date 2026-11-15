const VIEW_STYLE = Object.freeze({
    teamColors: { player: '#faC81E', squad: '#67D756', ally: '#174DFF', enemy: '#fa0C00', other: '#888888' },
    ownerColors: { ally: '#174DFF', enemy: '#fa0C00', neutral: '#ffffff' },
    maxColorDistance: 160,
    link: { ground: { maxStep: 0.03, maxGap: 3000 }, air: { maxStep: 0.06, maxGap: 3000 } },
    aliveWindow: 2000,
    deathMinPoints: 20,
    poiClusterRadius: 0.02,
    mapDim: 0.25,
    trackOrder: ['ally', 'other', 'enemy', 'squad', 'player'],
    lineWidth: { player: 3, squad: 2.5, enemy: 2, ally: 1.5, other: 1.5 },
    lineAlpha: { player: 1, squad: 1, enemy: 1, ally: 0.6, other: 0.6 },
    haloWidth: 2,
    haloColor: 'rgba(0,0,0,0.55)',
    current: { radius: 3, border: 1.5, playerScale: 1.4, playerRing: 2 },
    deathSize: 2.5,
    capture: { radius: 12, alpha: 0.3, border: 2 },
    respawn: { size: 8, alpha: 0.5, border: 1.5 },
    trailOptions: [10, 30, 60, 120, 0],
    fadeBands: 8,
    blipRange: [0.25, 1.5],
    lineScaleRange: [0.5, 2],
    speedRange: [5, 40],
    defaults: { trail: 30, blipSize: 0.5, lineScale: 1, speed: 10 },
    settingsKey: 'wtp.viewer',
});

const clamp = (value, [min, max]) => Math.max(min, Math.min(max, value));

class MatchViewer {
    constructor(canvasId, matchId, { isLive = false, battleType = 'ground', mapKind = 'ground', pollInterval = 500, onRender, onPlayStateChange } = {}) {
        this.canvas = document.getElementById(canvasId);
        this.ctx = this.canvas.getContext('2d');
        this.matchId = matchId;
        this.isLive = isLive;
        this.battleType = battleType;
        this.mapKind = mapKind;
        this.pollInterval = pollInterval;
        this.onRender = onRender;
        this.onPlayStateChange = onPlayStateChange;
        this.positions = [];
        this.positionCount = 0;
        this.pois = [];
        this.tracks = [];
        this.visiblePois = [];
        this.mapImage = null;
        this.lastTimestamp = 0;
        this.pollTimer = null;
        this.liveArmyType = 'tank';
        this.liveVehicleType = '';
        this.zoom = 1.0;
        this.minZoom = 0.5;
        this.maxZoom = 5.0;
        this.panX = 0;
        this.panY = 0;
        this.isPanning = false;
        this.lastMouseX = 0;
        this.lastMouseY = 0;
        const filters = { player: true, squad: true, ally: true, enemy: true, capture_zone: true, respawn: true, other: true };
        const settings = window.Settings.load(VIEW_STYLE.settingsKey, { ...VIEW_STYLE.defaults, filters });
        this.filters = { ...filters, ...settings.filters };
        this.blipSize = settings.blipSize;
        this.lineScale = settings.lineScale;
        this.trail = settings.trail;
        this.speed = settings.speed;
        this.timelinePosition = 1.0;
        this.maxTimestamp = 0;
        this.isPlaying = false;
        this.playbackFrame = null;
        this._resize();
        this._loadMap();
        this._setupInteractions();
        if (this.isLive) {
            this._startPolling();
        } else {
            this._loadPositions();
        }
        // 布局网格变化不一定触发窗口 resize，直接观察画布容器。
        new ResizeObserver(() => this._resize()).observe(this.canvas.parentElement);
    }

    _resize() {
        const container = this.canvas.parentElement;
        const padding = getComputedStyle(container);
        const width = container.clientWidth - parseFloat(padding.paddingLeft) - parseFloat(padding.paddingRight);
        const height = container.clientHeight - parseFloat(padding.paddingTop) - parseFloat(padding.paddingBottom);
        const size = Math.min(width, height, 1500);
        this.width = size;
        this.height = size;
        this.dpr = window.devicePixelRatio || 1;
        this.canvas.width = Math.round(size * this.dpr);
        this.canvas.height = Math.round(size * this.dpr);
        this.canvas.style.width = `${size}px`;
        this.canvas.style.height = `${size}px`;
        this._clampPan();
        this._render();
    }

    _setupInteractions() {
        this.canvas.addEventListener('wheel', (e) => {
            e.preventDefault();
            const rect = this.canvas.getBoundingClientRect();
            const mouseX = e.clientX - rect.left;
            const mouseY = e.clientY - rect.top;
            const zoomFactor = e.deltaY > 0 ? 0.9 : 1.1;
            const newZoom = Math.max(this.minZoom, Math.min(this.maxZoom, this.zoom * zoomFactor));

            if (newZoom !== this.zoom) {
                const zoomRatio = newZoom / this.zoom;
                this.panX = mouseX - (mouseX - this.panX) * zoomRatio;
                this.panY = mouseY - (mouseY - this.panY) * zoomRatio;
                this.zoom = newZoom;
                this._clampPan();
                this._render();
                this._updateZoomDisplay();
            }
        });
        this.canvas.addEventListener('mousedown', (e) => {
            if (e.button === 0) {
                this.isPanning = true;
                this.lastMouseX = e.clientX;
                this.lastMouseY = e.clientY;
                this.canvas.style.cursor = 'grabbing';
            }
        });

        window.addEventListener('mousemove', (e) => {
            if (this.isPanning) {
                const dx = e.clientX - this.lastMouseX;
                const dy = e.clientY - this.lastMouseY;
                this.panX += dx;
                this.panY += dy;
                this.lastMouseX = e.clientX;
                this.lastMouseY = e.clientY;
                this._clampPan();
                this._render();
            }
        });

        window.addEventListener('mouseup', () => {
            if (this.isPanning) {
                this.isPanning = false;
                this.canvas.style.cursor = 'grab';
            }
        });
        this.canvas.style.cursor = 'grab';
        this.canvas.addEventListener('dblclick', () => {
            this.resetView();
        });
    }

    _clampPan() {
        const w = this.width;
        const h = this.height;
        const scaledW = w * this.zoom;
        const scaledH = h * this.zoom;
        const margin = 50;
        this.panX = Math.max(-(scaledW - margin), Math.min(w - margin, this.panX));
        this.panY = Math.max(-(scaledH - margin), Math.min(h - margin, this.panY));
    }

    _updateZoomDisplay() {
        const zoomEl = document.getElementById('zoom-level');
        if (zoomEl) {
            zoomEl.textContent = `${Math.round(this.zoom * 100)}%`;
        }
    }

    resetView() {
        this.zoom = 1.0;
        this.panX = 0;
        this.panY = 0;
        this._render();
        this._updateZoomDisplay();
    }

    zoomIn() {
        const newZoom = Math.min(this.maxZoom, this.zoom * 1.25);
        if (newZoom !== this.zoom) {
            const cx = this.width / 2;
            const cy = this.height / 2;
            const zoomRatio = newZoom / this.zoom;
            this.panX = cx - (cx - this.panX) * zoomRatio;
            this.panY = cy - (cy - this.panY) * zoomRatio;
            this.zoom = newZoom;
            this._clampPan();
            this._render();
            this._updateZoomDisplay();
        }
    }

    zoomOut() {
        const newZoom = Math.max(this.minZoom, this.zoom / 1.25);
        if (newZoom !== this.zoom) {
            const cx = this.width / 2;
            const cy = this.height / 2;
            const zoomRatio = newZoom / this.zoom;
            this.panX = cx - (cx - this.panX) * zoomRatio;
            this.panY = cy - (cy - this.panY) * zoomRatio;
            this.zoom = newZoom;
            this._clampPan();
            this._render();
            this._updateZoomDisplay();
        }
    }

    get isAirMap() {
        return this.battleType === 'air' || this.mapKind === 'air';
    }

    setMapKind(kind) {
        this.mapKind = kind;
        this.mapImage = null;
        this._loadMap();
        this._buildTracks();
        this._render();
        this._updateStats();
    }

    async _loadMap() {
        const img = new Image();
        const kind = this.mapKind;
        img.onload = () => {
            // 切换过底图时丢弃旧请求的结果。
            if (kind !== this.mapKind) return;
            this.mapImage = img;
            this._render();
        };
        img.onerror = () => {
            console.warn('Failed to load map image');
            this._render();
        };
        img.src = `/api/match/${this.matchId}/map.png?kind=${kind}`;
    }

    async _loadPositions() {
        try {
            const resp = await fetch(`/api/match/${this.matchId}/positions?since=${this.lastTimestamp}`);
            const { ticks = [], positions = [] } = await resp.json();

            if (positions.length > 0) {
                const tickMap = new Map(ticks.map(tick => [tick.id, tick]));
                for (const pos of positions) {
                    const tick = tickMap.get(pos.tick_id);
                    if (!tick) continue;

                    this.maxTimestamp = Math.max(this.maxTimestamp, tick.timestamp);
                    this.lastTimestamp = Math.max(this.lastTimestamp, tick.timestamp + 1);
                    if (!pos.is_poi) this.positionCount++;

                    const merged = {
                        ...pos,
                        timestamp: tick.timestamp,
                        army_type: tick.army_type,
                        vehicle_type: tick.vehicle_type,
                        is_player_air: tick.is_player_air,
                        is_player_air_view: tick.is_player_air_view,
                    };
                    if (pos.is_poi) this.pois.push(merged);
                    else this.positions.push(merged);
                }
                this._buildTracks();
                this._render();
            }
        } catch (e) {
            console.error('Failed to load positions:', e);
        }
        this._updateStats();
    }

    _startPolling() {
        this.polling = true;
        this._poll();
    }

    // 串行轮询：上一轮请求结束后才安排下一轮，同一时刻只有一个位置请求。
    async _poll() {
        if (this.isLive) await this._loadPositions();
        await this._checkMatchStatus();
        if (this.polling) {
            this.pollTimer = setTimeout(() => this._poll(), this.pollInterval);
        }
    }

    _stopPolling() {
        this.polling = false;
        clearTimeout(this.pollTimer);
        this.pollTimer = null;
    }

    async _checkMatchStatus() {
        try {
            const resp = await fetch(`/api/match/${this.matchId}`);
            const match = await resp.json();
            if (match.ended_at) {
                const activeResp = await fetch('/api/active');
                const active = await activeResp.json();
                if (active && active.id && active.id !== this.matchId) {
                    window.location.href = '/live';
                } else if (this.isLive) {
                    // 结束前写入的最后一批位置可能还没取到，补取一次。
                    await this._loadPositions();
                    this.isLive = false;
                    this._showMatchEnded();
                }
            }
            const statusResp = await fetch('/api/status');
            const status = await statusResp.json();
            document.getElementById('capture-stopped').hidden = status.capturing;
            this.liveArmyType = status.army_type || 'tank';
            this.liveVehicleType = status.vehicle_type || '';
            this._updateStats();
        } catch (e) {
            console.error('Failed to check match status:', e);
        }
    }

    _showMatchEnded() {
        const badge = document.getElementById('live-badge');
        if (badge) {
            badge.textContent = t('match.ended');
            badge.classList.remove('live');
            badge.classList.add('ended');
        }
    }

    _updateStats() {
        const statsEl = document.getElementById('stats');
        if (!statsEl) return;

        const index = window.Tracks.lastIndexAtMost(this.positions, this._cutoff(), pos => pos.timestamp);
        const latest = this.positions[index];
        const armyType = (this.isLive ? this.liveArmyType : latest?.army_type) || 'tank';
        const vehicleType = (this.isLive ? this.liveVehicleType : '') || latest?.vehicle_type || '';
        const mode = document.createElement('span');
        mode.className = armyType === 'air' ? 'army-status air-info' : 'army-status';
        const airLabel = this.mapKind === 'air' ? t('viewer.air_view_raw') : t('viewer.air_view');
        mode.textContent = armyType === 'air' ? airLabel : t('viewer.ground');
        const counts = t('viewer.stats', { positions: this.positionCount, pois: this.poiCount });
        statsEl.replaceChildren(counts, document.createElement('br'), mode);
        if (vehicleType) {
            const vehicle = document.createElement('span');
            vehicle.className = 'vehicle-name';
            vehicle.textContent = vehicleType.split('/').at(-1).replace(/_/g, ' ');
            statsEl.append(document.createElement('br'), vehicle);
        }
    }

    _categorize(pos) {
        const type = pos.type.toLowerCase();
        if (type === 'capture_zone') return 'capture_zone';
        if (type.includes('respawn') || type.includes('airfield')) return 'respawn';
        return this._nearestColor(pos.color, VIEW_STYLE.teamColors, VIEW_STYLE.maxColorDistance);
    }

    _ownerColor(hex) {
        return VIEW_STYLE.ownerColors[this._nearestColor(hex, VIEW_STYLE.ownerColors)];
    }

    _nearestColor(hex, palette, maxDistance = Infinity) {
        const rgb = parseInt(hex.slice(1), 16);
        let best = 'other';
        let bestDistance = maxDistance ** 2;
        for (const [name, reference] of Object.entries(palette)) {
            const target = parseInt(reference.slice(1), 16);
            const dr = (rgb >> 16) - (target >> 16);
            const dg = (rgb >> 8 & 255) - (target >> 8 & 255);
            const db = (rgb & 255) - (target & 255);
            const distance = dr ** 2 + dg ** 2 + db ** 2;
            if (distance <= bestDistance) {
                best = name;
                bestDistance = distance;
            }
        }
        return best;
    }

    _isDrawable(pos) {
        // 空战图只画空中视角的原始坐标；纯空战图全部可画。
        if (this.mapKind === 'air') return Boolean(pos.is_player_air_view);
        if (this.battleType === 'air') return true;
        return pos.type.toLowerCase() !== 'aircraft' && (!pos.is_player_air_view || pos.x_ground != null);
    }

    // 返回当前底图上的显示坐标，越界返回 null。
    _displayPoint(pos) {
        const x = this.mapKind === 'air' ? pos.x : pos.x_ground ?? pos.x;
        const y = this.mapKind === 'air' ? pos.y : pos.y_ground ?? pos.y;
        return x >= 0 && x <= 1 && y >= 0 && y <= 1 ? { x, y } : null;
    }

    _buildTracks() {
        const grouped = new Map();
        for (const pos of this.positions) {
            if (!this._isDrawable(pos)) continue;
            const point = this._displayPoint(pos);
            if (!point) continue;
            const category = this._categorize(pos);
            if (!grouped.has(category)) grouped.set(category, new Map());
            const times = grouped.get(category);
            if (!times.has(pos.timestamp)) times.set(pos.timestamp, []);
            times.get(pos.timestamp).push(point);
        }
        this.visiblePois = [];
        for (const pos of this.pois) {
            const point = this._isDrawable(pos) && this._displayPoint(pos);
            if (point) this.visiblePois.push({ ...pos, ...point });
        }

        const options = this.isAirMap ? VIEW_STYLE.link.air : VIEW_STYLE.link.ground;
        this.tracks = [];
        for (const category of VIEW_STYLE.trackOrder) {
            if (!grouped.has(category)) continue;
            const frames = Array.from(grouped.get(category), ([t, points]) => ({ t, points }));
            frames.sort((a, b) => a.t - b.t);
            for (const points of window.Tracks.linkTracks(frames, options)) {
                this.tracks.push({ category, points });
            }
        }
    }

    _cutoff() {
        return this.isLive ? this.maxTimestamp : this.maxTimestamp * this.timelinePosition;
    }

    _getPoiClusters(cutoff) {
        const capture = [];
        const respawn = [];
        for (const pos of this.visiblePois) {
            if (pos.type.toLowerCase() === 'capture_zone') {
                if (pos.timestamp <= cutoff) capture.push(pos);
            } else {
                respawn.push(pos);
            }
        }
        const latest = group => group.reduce((a, b) => b.timestamp > a.timestamp ? b : a);
        return {
            capture: window.Tracks.clusterPoints(capture, VIEW_STYLE.poiClusterRadius, latest),
            respawn: window.Tracks.clusterPoints(respawn, VIEW_STYLE.poiClusterRadius, latest),
        };
    }

    _render() {
        const ctx = this.ctx;
        const w = this.width;
        const h = this.height;
        ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
        ctx.fillStyle = '#1a1a1a';
        ctx.fillRect(0, 0, w, h);
        ctx.save();
        ctx.translate(this.panX, this.panY);
        ctx.scale(this.zoom, this.zoom);
        ctx.lineJoin = 'round';
        ctx.lineCap = 'round';
        if (this.mapImage) {
            ctx.drawImage(this.mapImage, 0, 0, w, h);
        } else {
            ctx.strokeStyle = '#333';
            ctx.lineWidth = 1 / this.zoom;
            for (let i = 0; i <= 10; i++) {
                const fraction = i / 10;
                ctx.beginPath();
                ctx.moveTo(fraction * w, 0);
                ctx.lineTo(fraction * w, h);
                ctx.moveTo(0, fraction * h);
                ctx.lineTo(w, fraction * h);
                ctx.stroke();
            }
        }
        ctx.fillStyle = `rgba(0,0,0,${VIEW_STYLE.mapDim})`;
        ctx.fillRect(0, 0, w, h);

        const cutoff = this._cutoff();
        const { capture, respawn } = this._getPoiClusters(cutoff);
        this.poiCount = capture.length + respawn.length;
        if (this.filters.capture_zone) {
            for (const point of capture) this._drawPoi(point, true);
        }
        if (this.filters.respawn) {
            for (const point of respawn) this._drawPoi(point, false);
        }

        const current = [];
        const deaths = [];
        for (const { category, points } of this.tracks) {
            if (!this.filters[category]) continue;
            const [start, end] = this._visibleRange(points, cutoff);
            if (start > end) continue;
            if (end > start) this._drawTrack(category, points, start, end, cutoff - this.trail * 1000);
            const point = points[end];
            if (cutoff - point.t <= VIEW_STYLE.aliveWindow) {
                current.push({ category, point });
            } else if (end === points.length - 1 && points.length >= VIEW_STYLE.deathMinPoints &&
                point.t < this.maxTimestamp - VIEW_STYLE.aliveWindow) {
                deaths.push({ category, point });
            }
        }
        for (const { category, point } of current) this._drawCurrent(category, point);
        for (const { category, point } of deaths) this._drawDeath(category, point);

        ctx.restore();
        this.onRender?.(this);
    }

    _drawTrack(category, points, start, end, earliest) {
        const ctx = this.ctx;
        for (const band of this._fadeBands(points, start, end, earliest)) {
            ctx.beginPath();
            ctx.moveTo(points[band.from].x * this.width, points[band.from].y * this.height);
            for (let i = band.from + 1; i <= band.to; i++) {
                ctx.lineTo(points[i].x * this.width, points[i].y * this.height);
            }
            this._strokeTrack(category, VIEW_STYLE.lineAlpha[category] * band.alpha);
        }
    }

    // 把可见段按时间等分成若干段，越旧越透明；显示全部时不淡化。
    _fadeBands(points, start, end, earliest) {
        if (this.trail === 0) return [{ from: start, to: end, alpha: 1 }];
        const span = this.trail * 1000;
        const count = VIEW_STYLE.fadeBands;
        const bands = [];
        let from = start;
        for (let k = 1; k <= count && from < end; k++) {
            const limit = earliest + span * k / count;
            let to = k === count ? end : Math.max(from + 1, window.Tracks.lastIndexAtMost(points, limit, p => p.t));
            to = Math.min(to, end);
            const mid = (points[from].t + points[to].t) / 2;
            bands.push({ from, to, alpha: Math.max(0, Math.min(1, (mid - earliest) / span)) });
            from = to;
        }
        return bands;
    }

    _strokeTrack(category, alpha) {
        const ctx = this.ctx;
        const width = VIEW_STYLE.lineWidth[category] * this.lineScale;
        ctx.lineWidth = (width + VIEW_STYLE.haloWidth) / this.zoom;
        ctx.strokeStyle = VIEW_STYLE.haloColor;
        ctx.globalAlpha = alpha;
        ctx.stroke();
        ctx.lineWidth = width / this.zoom;
        ctx.strokeStyle = VIEW_STYLE.teamColors[category];
        ctx.globalAlpha = alpha;
        ctx.stroke();
        ctx.globalAlpha = 1;
    }

    _drawPoi(point, isCapture) {
        const ctx = this.ctx;
        const x = point.x * this.width;
        const y = point.y * this.height;
        const style = isCapture ? VIEW_STYLE.capture : VIEW_STYLE.respawn;
        const color = this._ownerColor(point.color);
        ctx.beginPath();
        if (isCapture) {
            ctx.arc(x, y, style.radius / this.zoom, 0, Math.PI * 2);
        } else {
            const size = style.size / this.zoom;
            ctx.rect(x - size / 2, y - size / 2, size, size);
        }
        ctx.lineWidth = (style.border + VIEW_STYLE.haloWidth) / this.zoom;
        ctx.strokeStyle = VIEW_STYLE.haloColor;
        ctx.stroke();
        ctx.globalAlpha = style.alpha;
        ctx.fillStyle = color;
        ctx.fill();
        ctx.globalAlpha = 1;
        ctx.lineWidth = style.border / this.zoom;
        ctx.strokeStyle = color;
        ctx.stroke();
    }

    _drawCurrent(category, point) {
        const ctx = this.ctx;
        const style = VIEW_STYLE.current;
        const x = point.x * this.width;
        const y = point.y * this.height;
        const radius = this.blipSize * style.radius * (category === 'player' ? style.playerScale : 1) / this.zoom;
        ctx.beginPath();
        ctx.arc(x, y, radius, 0, Math.PI * 2);
        ctx.fillStyle = VIEW_STYLE.teamColors[category];
        ctx.fill();
        ctx.strokeStyle = '#000';
        ctx.lineWidth = style.border / this.zoom;
        ctx.stroke();
        if (category === 'player') {
            ctx.beginPath();
            ctx.arc(x, y, radius + (style.border + style.playerRing) / 2 / this.zoom, 0, Math.PI * 2);
            ctx.strokeStyle = '#fff';
            ctx.lineWidth = style.playerRing / this.zoom;
            ctx.stroke();
        }
    }

    _drawDeath(category, point) {
        const ctx = this.ctx;
        const x = point.x * this.width;
        const y = point.y * this.height;
        const half = this.blipSize * VIEW_STYLE.deathSize / 2 / this.zoom;
        ctx.beginPath();
        ctx.moveTo(x - half, y - half);
        ctx.lineTo(x + half, y + half);
        ctx.moveTo(x + half, y - half);
        ctx.lineTo(x - half, y + half);
        this._strokeTrack(category, 1);
    }

    _saveSettings() {
        window.Settings.save(VIEW_STYLE.settingsKey, {
            trail: this.trail, blipSize: this.blipSize, lineScale: this.lineScale, speed: this.speed, filters: this.filters,
        });
    }

    setFilter(category, enabled) {
        this.filters[category] = enabled;
        this._saveSettings();
        this._render();
    }

    setBlipSize(size) {
        this.blipSize = clamp(size, VIEW_STYLE.blipRange);
        this._saveSettings();
        this._render();
    }

    setLineScale(scale) {
        this.lineScale = clamp(scale, VIEW_STYLE.lineScaleRange);
        this._saveSettings();
        this._render();
    }

    setSpeed(speed) {
        this.speed = clamp(speed, VIEW_STYLE.speedRange);
        this._saveSettings();
    }

    setTrail(seconds) {
        this.trail = seconds;
        this._saveSettings();
        this._render();
    }

    _visibleRange(points, cutoff) {
        const timeOf = point => point.t;
        const end = window.Tracks.lastIndexAtMost(points, cutoff, timeOf);
        if (this.trail === 0) return [0, end];
        const earliest = cutoff - this.trail * 1000;
        const index = window.Tracks.lastIndexAtMost(points, earliest, timeOf);
        const start = index >= 0 && points[index].t === earliest ? index : index + 1;
        return [start, end];
    }

    play() {
        if (this.isLive || this.isPlaying || this.maxTimestamp === 0) return;
        if (this.timelinePosition === 1) this.setTimeline(0);
        this.isPlaying = true;
        this.onPlayStateChange?.(true);
        let lastTime;
        const frame = now => {
            if (lastTime !== undefined) this._advancePlayback(now - lastTime);
            lastTime = now;
            if (this.isPlaying) this.playbackFrame = requestAnimationFrame(frame);
        };
        this.playbackFrame = requestAnimationFrame(frame);
    }

    pause() {
        if (!this.isPlaying) return;
        this.isPlaying = false;
        cancelAnimationFrame(this.playbackFrame);
        this.playbackFrame = null;
        this.onPlayStateChange?.(false);
    }

    _advancePlayback(dt) {
        this.setTimeline(this.timelinePosition + dt * this.speed / this.maxTimestamp);
        if (this.timelinePosition === 1) this.pause();
    }

    setTimeline(position) {
        this.timelinePosition = Math.max(0, Math.min(1, position));
        this._render();
        this._updateStats();
    }

    getTimelineMax() {
        return this.maxTimestamp;
    }

    formatTime(seconds) {
        const totalSeconds = Math.floor(seconds / 1000);
        const mins = Math.floor(totalSeconds / 60);
        const secs = Math.floor(totalSeconds % 60);
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    }

    destroy() {
        this.pause();
        this._stopPolling();
    }
}
window.MatchViewer = MatchViewer;
