const VIEW_STYLE = Object.freeze({
    teamColors: { player: '#faC81E', squad: '#67D756', ally: '#174DFF', enemy: '#fa0C00', other: '#888888' },
    ownerColors: { ally: '#174DFF', enemy: '#fa0C00', neutral: '#ffffff' },
    maxColorDistance: 160,
    // 实测（2026-11-15 七场数据）：坦克与喷气机在归一化坐标中最快约 0.005/秒，取约 1.6 倍余量。
    // 未被发现的敌机会从地图上消失 2～5 秒，maxGap 允许其重新接上。
    link: { maxSpeed: 0.008, jitter: 0.002, maxGap: 6000 },
    // 相邻两点间隔超过它就视为不可见期间，不画连线。
    gapLine: 1000,
    // 敌方只在被发现时出现在地图上，消失不等于阵亡，只给这些阵营画 ×。
    deathCategories: ['player', 'squad', 'ally'],
    aliveWindow: 2000,
    deathMinPoints: 20,
    poiClusterRadius: 0.02,
    mapDim: 0.25,
    trackOrder: ['ally', 'other', 'enemy', 'squad', 'player'],
    lineWidth: { player: 3, squad: 2.5, enemy: 2, ally: 1.5, other: 1.5 },
    lineAlpha: { player: 1, squad: 1, enemy: 1, ally: 0.6, other: 0.6 },
    haloWidth: 2,
    haloColor: 'rgba(0,0,0,0.55)',
    // 当前位置标记：屏幕尺寸 = blipSize × markerBase × scale。
    markerBase: 14,
    current: { border: 1.5, playerScale: 1.4, playerRing: 2 },
    playerIcon: 'Player',
    unitShapes: {
        LightTank: { shape: 'diamond', scale: 1 },
        MediumTank: { shape: 'circle', scale: 1 },
        HeavyTank: { shape: 'square', scale: 0.9 },
        TankDestroyer: { shape: 'triangle', scale: 1 },
        SPAA: { shape: 'circle-cross', scale: 1 },
        SAM: { shape: 'circle-cross', scale: 1 },
        Wheeled: { shape: 'pentagon', scale: 1 },
        IFV: { shape: 'pentagon', scale: 1 },
        Fighter: { shape: 'arrow', scale: 1 },
        Assault: { shape: 'arrow', scale: 1.15 },
        Bomber: { shape: 'arrow', scale: 1.3 },
    },
    hoverSlop: 4,
    deathScale: 0.8,
    capture: { radius: 12, alpha: 0.3, border: 2 },
    respawn: { size: 8, alpha: 0.5, border: 1.5 },
    trailOptions: [10, 30, 60, 120, 0],
    // 轨迹渐隐的不透明度档数；档数越多越平滑，绘制也越慢。
    fadeLevels: 40,
    blipRange: [0.25, 1.5],
    lineScaleRange: [0.5, 2],
    speedRange: [5, 40],
    defaults: { trail: 30, blipSize: 0.5, lineScale: 1, speed: 10 },
    settingsKey: 'wtp.viewer',
});

const clamp = (value, [min, max]) => Math.max(min, Math.min(max, value));

class MatchViewer {
    constructor(canvasId, matchId, { isLive = false, battleType = 'ground', mapKind = 'ground', pollInterval = 500, onRender, onPlayStateChange, onEvents } = {}) {
        this.canvas = document.getElementById(canvasId);
        this.ctx = this.canvas.getContext('2d');
        this.matchId = matchId;
        this.isLive = isLive;
        this.battleType = battleType;
        this.mapKind = mapKind;
        this.pollInterval = pollInterval;
        this.onRender = onRender;
        this.onPlayStateChange = onPlayStateChange;
        this.onEvents = onEvents;
        this.events = [];
        this.lastEventTimestamp = 0;
        this.feedKey = '';
        this.positions = [];
        this.positionCount = 0;
        this.pois = [];
        this.tracks = [];
        this.markers = [];
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
        this.trackLayer = document.createElement('canvas');
        this._resize();
        this._loadMap();
        this._setupInteractions();
        if (this.isLive) {
            this._startPolling();
        } else {
            this._loadPositions();
            this._loadEvents();
        }
        // 布局网格变化不一定触发窗口 resize，直接观察画布容器。
        new ResizeObserver(() => this._resize()).observe(this.canvas.parentElement);
    }

    _resize() {
        const container = this.canvas.parentElement;
        const padding = getComputedStyle(container);
        const width = container.clientWidth - parseFloat(padding.paddingLeft) - parseFloat(padding.paddingRight);
        const height = container.clientHeight - parseFloat(padding.paddingTop) - parseFloat(padding.paddingBottom);
        // 画布铺满容器；地图仍是正方形（width/height 为地图边长），居中放置。
        const size = Math.min(width, height);
        const [oldX, oldY] = this.viewWidth === undefined ? [0, 0] : this._centerOffset();
        this.width = size;
        this.height = size;
        this.viewWidth = width;
        this.viewHeight = height;
        const [newX, newY] = this._centerOffset();
        this.panX += newX - oldX;
        this.panY += newY - oldY;
        this.dpr = window.devicePixelRatio || 1;
        this.canvas.width = Math.round(width * this.dpr);
        this.canvas.height = Math.round(height * this.dpr);
        this.trackLayer.width = this.canvas.width;
        this.trackLayer.height = this.canvas.height;
        this.canvas.style.width = `${width}px`;
        this.canvas.style.height = `${height}px`;
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

        this.canvas.addEventListener('mousemove', (e) => this._showTooltip(e));
        this.canvas.addEventListener('mouseleave', () => { document.getElementById('unit-tooltip').hidden = true; });

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

    _showTooltip(e) {
        const tooltip = document.getElementById('unit-tooltip');
        const rect = this.canvas.getBoundingClientRect();
        const hit = this.isPanning ? null : this._markerAt(e.clientX - rect.left, e.clientY - rect.top);
        tooltip.hidden = !hit;
        if (!hit) return;
        tooltip.textContent = this._markerLabel(hit);
        const wrapper = this.canvas.parentElement.getBoundingClientRect();
        tooltip.style.left = `${e.clientX - wrapper.left + 12}px`;
        tooltip.style.top = `${e.clientY - wrapper.top + 12}px`;
    }

    // 缩放为 1 时让地图居中的平移量。
    _centerOffset() {
        return [(this.viewWidth - this.width) / 2, (this.viewHeight - this.height) / 2];
    }

    // 兵种名；已知具体型号（只有自己）时一并显示。
    _markerLabel(marker) {
        const name = t(`unit.${marker.icon}`);
        return marker.vehicle ? `${name} · ${this._vehicleName(marker.vehicle)}` : name;
    }

    _vehicleName(raw) {
        return raw.split('/').at(-1).replace(/_/g, ' ');
    }

    _clampPan() {
        const scaledW = this.width * this.zoom;
        const scaledH = this.height * this.zoom;
        const margin = 50;
        this.panX = Math.max(-(scaledW - margin), Math.min(this.viewWidth - margin, this.panX));
        this.panY = Math.max(-(scaledH - margin), Math.min(this.viewHeight - margin, this.panY));
    }

    _updateZoomDisplay() {
        const zoomEl = document.getElementById('zoom-level');
        if (zoomEl) {
            zoomEl.textContent = `${Math.round(this.zoom * 100)}%`;
        }
    }

    resetView() {
        this.zoom = 1.0;
        [this.panX, this.panY] = this._centerOffset();
        this._render();
        this._updateZoomDisplay();
    }

    zoomIn() {
        const newZoom = Math.min(this.maxZoom, this.zoom * 1.25);
        if (newZoom !== this.zoom) {
            const cx = this.viewWidth / 2;
            const cy = this.viewHeight / 2;
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
            const cx = this.viewWidth / 2;
            const cy = this.viewHeight / 2;
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
                    // 不显示的单位（火炮、碉堡、舰船等）直接丢弃。
                    if (!pos.is_poi && !this._isShownUnit(pos)) continue;

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

    async _loadEvents() {
        const resp = await fetch(`/api/match/${this.matchId}/events?since=${this.lastEventTimestamp}`);
        const events = await resp.json();
        if (events.length === 0) return;
        for (const event of events) this.events.push(event);
        this.lastEventTimestamp = events.at(-1).timestamp + 1;
        this._render();
    }

    // 时间轴当前时刻之前的播报，最新的在前。
    _visibleEvents(cutoff) {
        const end = window.Tracks.lastIndexAtMost(this.events, cutoff, event => event.timestamp);
        return this.events.slice(0, end + 1).reverse();
    }

    _startPolling() {
        this.polling = true;
        this._poll();
    }

    // 串行轮询：上一轮请求结束后才安排下一轮，同一时刻只有一个位置请求。
    async _poll() {
        if (this.isLive) await Promise.all([this._loadPositions(), this._loadEvents()]);
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
                    await Promise.all([this._loadPositions(), this._loadEvents()]);
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
            vehicle.textContent = this._vehicleName(vehicleType);
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

    _isShownUnit(pos) {
        return pos.icon === VIEW_STYLE.playerIcon || pos.icon in VIEW_STYLE.unitShapes;
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
            const vehicle = pos.icon === VIEW_STYLE.playerIcon ? pos.vehicle_type : '';
            times.get(pos.timestamp).push({ ...point, icon: pos.icon, vehicle });
        }
        this.visiblePois = [];
        for (const pos of this.pois) {
            const point = this._isDrawable(pos) && this._displayPoint(pos);
            if (point) this.visiblePois.push({ ...pos, ...point });
        }

        this.tracks = [];
        for (const category of VIEW_STYLE.trackOrder) {
            if (!grouped.has(category)) continue;
            const frames = Array.from(grouped.get(category), ([t, points]) => ({ t, points }));
            frames.sort((a, b) => a.t - b.t);
            for (const points of window.Tracks.linkTracks(frames, VIEW_STYLE.link)) {
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
        ctx.fillRect(0, 0, this.viewWidth, this.viewHeight);
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
        const fades = new Map();
        for (const { category, points } of this.tracks) {
            if (!this.filters[category]) continue;
            const [start, end] = this._visibleRange(points, cutoff);
            if (start > end) continue;
            if (!fades.has(category)) fades.set(category, []);
            this._addTrack(fades.get(category), points, start, end, cutoff - this.trail * 1000);
            const point = points[end];
            if (cutoff - point.t <= VIEW_STYLE.aliveWindow) {
                current.push({ category, point, previous: points[end - 1] });
            } else if (this._isDeath(category, points, end, cutoff)) {
                deaths.push({ category, point });
            }
        }
        this._drawFades(fades);
        this.markers = [];
        for (const { category, point, previous } of current) this._drawCurrent(category, point, previous);
        for (const { category, point } of deaths) this._drawDeath(category, point);

        ctx.restore();
        this.onRender?.(this);
        this._emitEvents(cutoff);
    }

    // 播报列表有变化时才通知页面重绘。
    _emitEvents(cutoff) {
        const visible = this._visibleEvents(cutoff);
        const key = `${visible.length}:${visible[0]?.timestamp}`;
        if (key === this.feedKey) return;
        this.feedKey = key;
        this.onEvents?.(visible);
    }

    // 轨迹已结束且不可能再接上（超过 maxGap），并且该阵营总在地图上可见。
    _isDeath(category, points, end, cutoff) {
        const last = points[end];
        return VIEW_STYLE.deathCategories.includes(category) &&
            end === points.length - 1 &&
            points.length >= VIEW_STYLE.deathMinPoints &&
            last.t < cutoff - VIEW_STYLE.link.maxGap &&
            last.t < this.maxTimestamp - VIEW_STYLE.link.maxGap;
    }

    _isGap(previous, point) {
        return point.t - previous.t > VIEW_STYLE.gapLine;
    }

    // 一小段线的不透明度：按中点时刻在显示窗口内线性变化，显示全部时不淡化。
    _fadeAlpha(previous, point, earliest) {
        if (this.trail === 0) return 1;
        return clamp(((previous.t + point.t) / 2 - earliest) / (this.trail * 1000), [0, 1]);
    }

    // 把轨迹的每一小段加入它所在档位的路径；levels[档位] 是该档所有线段合成的一条路径。
    _addTrack(levels, points, start, end, earliest) {
        let lastLevel = -1;
        for (let i = start + 1; i <= end; i++) {
            if (this._isGap(points[i - 1], points[i])) {
                lastLevel = -1;
                continue;
            }
            const level = Math.round(this._fadeAlpha(points[i - 1], points[i], earliest) * VIEW_STYLE.fadeLevels);
            const path = levels[level] ??= new Path2D();
            if (level !== lastLevel) path.moveTo(points[i - 1].x * this.width, points[i - 1].y * this.height);
            path.lineTo(points[i].x * this.width, points[i].y * this.height);
            lastLevel = level;
        }
    }

    // 轨迹画在单独的图层上，从旧到新逐档描边；每档先擦掉自己要盖住的区域，
    // 半透明的线在接头和交叉处就不会叠深，看起来是连续的渐变。
    _drawFades(fades) {
        const layer = this.trackLayer.getContext('2d');
        layer.setTransform(1, 0, 0, 1, 0, 0);
        layer.clearRect(0, 0, this.trackLayer.width, this.trackLayer.height);
        layer.setTransform(this.ctx.getTransform());
        layer.lineJoin = 'round';
        layer.lineCap = 'round';
        for (const [category, levels] of fades) {
            const width = VIEW_STYLE.lineWidth[category] * this.lineScale / this.zoom;
            const halo = width + VIEW_STYLE.haloWidth / this.zoom;
            // 先画完各档的黑边再画本色，新一段的黑边不会压在上一段的本色上。
            for (const [lineWidth, color] of [[halo, VIEW_STYLE.haloColor], [width, VIEW_STYLE.teamColors[category]]]) {
                layer.lineWidth = lineWidth;
                levels.forEach((path, level) => {
                    if (level === 0) return;
                    layer.globalCompositeOperation = 'destination-out';
                    layer.globalAlpha = 1;
                    layer.strokeStyle = '#000';
                    layer.stroke(path);
                    layer.globalCompositeOperation = 'source-over';
                    layer.globalAlpha = VIEW_STYLE.lineAlpha[category] * level / VIEW_STYLE.fadeLevels;
                    layer.strokeStyle = color;
                    layer.stroke(path);
                });
            }
        }
        layer.globalAlpha = 1;
        this.ctx.save();
        this.ctx.setTransform(1, 0, 0, 1, 0, 0);
        this.ctx.drawImage(this.trackLayer, 0, 0);
        this.ctx.restore();
    }

    // 给阵亡标记描黑边和本色。
    _strokeMark(category, path) {
        const ctx = this.ctx;
        const width = VIEW_STYLE.lineWidth[category] * this.lineScale;
        ctx.lineWidth = (width + VIEW_STYLE.haloWidth) / this.zoom;
        ctx.strokeStyle = VIEW_STYLE.haloColor;
        ctx.stroke(path);
        ctx.lineWidth = width / this.zoom;
        ctx.strokeStyle = VIEW_STYLE.teamColors[category];
        ctx.stroke(path);
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

    _drawCurrent(category, point, previous) {
        const ctx = this.ctx;
        const style = VIEW_STYLE.current;
        const x = point.x * this.width;
        const y = point.y * this.height;
        const isPlayer = point.icon === VIEW_STYLE.playerIcon;
        const unit = VIEW_STYLE.unitShapes[point.icon];
        const scale = isPlayer ? style.playerScale : unit.scale;
        const size = this.blipSize * VIEW_STYLE.markerBase * scale / this.zoom;
        // 箭头沿最后一段轨迹的方向，只有一个点时朝上。
        const angle = previous ? Math.atan2(point.y - previous.y, point.x - previous.x) : -Math.PI / 2;
        window.Shapes.path(ctx, isPlayer ? 'circle' : unit.shape, x, y, size, angle);
        ctx.fillStyle = VIEW_STYLE.teamColors[category];
        ctx.fill();
        ctx.strokeStyle = '#000';
        ctx.lineWidth = style.border / this.zoom;
        ctx.stroke();
        if (isPlayer) {
            ctx.beginPath();
            ctx.arc(x, y, size / 2 + (style.border + style.playerRing) / 2 / this.zoom, 0, Math.PI * 2);
            ctx.strokeStyle = '#fff';
            ctx.lineWidth = style.playerRing / this.zoom;
            ctx.stroke();
        }
        this.markers.push({
            sx: x * this.zoom + this.panX, sy: y * this.zoom + this.panY, r: size * this.zoom / 2,
            icon: point.icon, vehicle: point.vehicle,
        });
    }

    // 返回屏幕坐标下最近的当前位置标记。
    _markerAt(sx, sy) {
        let best = null;
        let bestDistance = Infinity;
        for (const marker of this.markers) {
            const distance = Math.hypot(marker.sx - sx, marker.sy - sy);
            if (distance <= marker.r + VIEW_STYLE.hoverSlop && distance < bestDistance) {
                best = marker;
                bestDistance = distance;
            }
        }
        return best;
    }

    _drawDeath(category, point) {
        const x = point.x * this.width;
        const y = point.y * this.height;
        const half = this.blipSize * VIEW_STYLE.markerBase * VIEW_STYLE.deathScale / 2 / this.zoom;
        const cross = new Path2D();
        cross.moveTo(x - half, y - half);
        cross.lineTo(x + half, y + half);
        cross.moveTo(x + half, y - half);
        cross.lineTo(x - half, y + half);
        this._strokeMark(category, cross);
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
