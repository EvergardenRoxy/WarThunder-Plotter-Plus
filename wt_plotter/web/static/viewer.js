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
        Boat: { shape: 'ship', scale: 0.85 },
        HeavyBoat: { shape: 'ship', scale: 0.95 },
        Barge: { shape: 'ship', scale: 0.95 },
        Frigate: { shape: 'ship', scale: 1 },
        Destroyer: { shape: 'ship', scale: 1.05 },
        MissileDestroyer: { shape: 'ship', scale: 1.1 },
        LightCruiser: { shape: 'ship', scale: 1.2 },
        HeavyCruiser: { shape: 'ship', scale: 1.3 },
        Battlecruiser: { shape: 'ship', scale: 1.4 },
        Battleship: { shape: 'ship', scale: 1.5 },
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
    mapDimRange: [0, 0.6],
    feedFilters: Object.freeze(['all', 'kill', 'award', 'no_leave']),
    speedOptions: Object.freeze([0.5, 1, 2, 5, 8, 10, 15, 20, 25, 40, 50]),
    defaults: {
        trail: 30, blipSize: 0.5, lineScale: 1, mapDim: 0.25, speed: 10,
        showAllFriendlyDeaths: false, followFeed: true, followPlayer: false,
        sidebarCollapsed: false, feedFilter: 'all',
    },
    settingsKey: 'wtp.viewer',
});

const clamp = (value, [min, max]) => Math.max(min, Math.min(max, value));
const nearestSpeed = value => VIEW_STYLE.speedOptions.reduce((best, speed) =>
    Math.abs(speed - value) < Math.abs(best - value) ? speed : best
);

class MatchViewer {
    constructor(canvasId, matchId, {
        isLive = false, battleType = 'ground', mapKind = 'ground', replayTracks = false, pollInterval = 500,
        placeholderVehicles = [], onRender, onPlayStateChange, onEvents, onMapUpdate, onFollowPlayerChange,
    } = {}) {
        this.canvas = document.getElementById(canvasId);
        this.ctx = this.canvas.getContext('2d');
        this.matchId = matchId;
        this.isLive = isLive;
        this.battleType = battleType;
        // 轨迹由录像还原：陆战里的飞机坐标与地面单位同一套，可以画。
        this.replayTracks = replayTracks;
        this.mapKind = mapKind;
        this.mapKindSelected = false;
        this.pollInterval = pollInterval;
        this.onRender = onRender;
        this.onPlayStateChange = onPlayStateChange;
        this.onEvents = onEvents;
        this.onMapUpdate = onMapUpdate;
        this.onFollowPlayerChange = onFollowPlayerChange;
        this.events = [];
        this.lastEventTimestamp = 0;
        this.selectedEvent = null;
        this.ticks = [];
        this.playerTickIds = new Set();
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
        this.placeholderVehicles = placeholderVehicles;
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
        this.mapDim = clamp(settings.mapDim, VIEW_STYLE.mapDimRange);
        this.trail = settings.trail;
        this.speed = nearestSpeed(settings.speed);
        this.showAllFriendlyDeaths = settings.showAllFriendlyDeaths;
        this.followFeed = settings.followFeed;
        this.followPlayer = Boolean(settings.followPlayer);
        this.sidebarCollapsed = Boolean(settings.sidebarCollapsed);
        this.feedFilter = VIEW_STYLE.feedFilters.includes(settings.feedFilter) ? settings.feedFilter : 'all';
        // null 表示跟随最新时刻，倒带时保存固定的比赛内毫秒数。
        this.selectedTime = null;
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
                if ((dx || dy) && this.followPlayer) {
                    this.followPlayer = false;
                    this._saveSettings();
                    this.onFollowPlayerChange?.(false);
                }
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
        tooltip.style.left = `${Math.min(e.clientX - wrapper.left + 12, wrapper.width - tooltip.offsetWidth)}px`;
        tooltip.style.top = `${Math.min(e.clientY - wrapper.top + 12, wrapper.height - tooltip.offsetHeight)}px`;
    }

    // 缩放为 1 时让地图居中的平移量。
    _centerOffset() {
        return [(this.viewWidth - this.width) / 2, (this.viewHeight - this.height) / 2];
    }

    // 兵种名；已知玩家名（录像）、具体型号、阵亡时间或占领点时附带状态信息。
    _markerLabel(marker) {
        if (marker.kind === 'capture_zone') {
            return t('viewer.capture_zone_tooltip', {
                owner: t(`viewer.owner_${marker.owner}`),
                time: this.formatTime(marker.timestamp),
            });
        }
        const unit = t(`unit.${marker.icon}`);
        const kind = marker.vehicle ? `${unit} · ${this._vehicleName(marker.vehicle)}` : unit;
        const base = marker.name ? `${marker.name} · ${kind}` : kind;
        if (marker.deathTime !== undefined) {
            return t('viewer.marker_knocked_out', { unit: base, time: this.formatTime(marker.deathTime) });
        }
        return base;
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

    setMapKind(kind, manual = true) {
        if (manual) this.mapKindSelected = true;
        if (kind === this.mapKind) return;
        this.mapKind = kind;
        this.mapImage = null;
        this._loadMap();
        this._buildTracks();
        this._render();
        this._updateStats();
    }

    _applyMapMetadata(match) {
        const battleTypeChanged = this.battleType !== match.battle_type || this.replayTracks !== match.replay_tracks;
        this.battleType = match.battle_type;
        this.replayTracks = match.replay_tracks;
        if (this.isAtLatest && !this.mapKindSelected && this.mapKind !== match.default_map) {
            this.setMapKind(match.default_map, false);
        } else if (battleTypeChanged) {
            this._buildTracks();
            this._render();
        }
        this.onMapUpdate?.(this, match);
    }

    _loadMap() {
        const kind = this.mapKind;
        if (this.mapRequest?.kind === kind) return;
        const img = new Image();
        const request = { kind };
        this.mapRequest = request;
        img.onload = () => {
            // 切换过底图时丢弃旧请求的结果。
            if (this.mapRequest !== request) return;
            this.mapRequest = null;
            this.mapImage = img;
            this._render();
        };
        img.onerror = () => {
            if (this.mapRequest === request) this.mapRequest = null;
        };
        img.src = `/api/match/${this.matchId}/map.png?kind=${kind}`;
    }

    async _loadPositions() {
        try {
            const resp = await fetch(`/api/match/${this.matchId}/positions?since=${this.lastTimestamp}`);
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const { ticks = [], positions = [] } = await resp.json();

            if (ticks.length > 0) {
                const tickMap = new Map(ticks.map(tick => [tick.id, tick]));
                for (const tick of ticks) this.ticks.push(tick);
                this.maxTimestamp = Math.max(this.maxTimestamp, ticks.at(-1).timestamp);
                this.lastTimestamp = this.maxTimestamp + 1;
                for (const pos of positions) {
                    const tick = tickMap.get(pos.tick_id);
                    if (!tick) continue;

                    if (!pos.is_poi) {
                        this.positionCount++;
                        if (pos.icon === VIEW_STYLE.playerIcon) this.playerTickIds.add(pos.tick_id);
                    }
                    // 不显示的单位（火炮、碉堡、防空炮等）直接丢弃。
                    if (!pos.is_poi && !this._isShownUnit(pos)) continue;

                    const merged = {
                        ...pos,
                        timestamp: tick.timestamp,
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
            return false;
        }
        this._updateStats();
        return true;
    }

    async _loadEvents() {
        let events;
        try {
            const resp = await fetch(`/api/match/${this.matchId}/events?since=${this.lastEventTimestamp}`);
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            events = await resp.json();
        } catch (e) {
            console.error('Failed to load events:', e);
            return false;
        }
        if (events.length > 0) {
            for (const event of events) this.events.push(event);
            this.lastEventTimestamp = events.at(-1).timestamp + 1;
            this.onEvents?.(events, this);
            this._render();
        }
        return true;
    }

    _startPolling() {
        this.polling = true;
        this._poll();
    }

    // 串行轮询：上一轮请求结束后才安排下一轮，同一时刻只有一个位置请求。
    async _poll() {
        if (this.isLive) await Promise.all([this._loadPositions(), this._loadEvents()]);
        await this._checkMatchStatus();
        // 开局时底图可能还没画完，服务端拿到完整底图前一直重试。
        if (this.isLive && !this.mapImage) this._loadMap();
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
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const match = await resp.json();
            this._applyMapMetadata(match);
            if (match.ended_at) {
                if (this.isAtLatest) {
                    const activeResp = await fetch('/api/active');
                    const active = await activeResp.json();
                    if (this.isAtLatest && active && active.id !== this.matchId) {
                        window.location.href = '/live';
                        return;
                    }
                }
                if (this.isLive) {
                    // 倒带时留在这局，补齐最后的位置和播报。
                    const loaded = await Promise.all([this._loadPositions(), this._loadEvents()]);
                    if (loaded.every(Boolean)) {
                        this.isLive = false;
                        this._showMatchEnded();
                        this._render();
                    }
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

        const index = window.Tracks.lastIndexAtMost(this.ticks, this.getTimelineTime(), tick => tick.timestamp);
        const latest = this.ticks[index];
        const followingLive = this.isLive && this.isAtLatest;
        const armyType = (followingLive ? this.liveArmyType : latest?.army_type) || 'tank';
        const vehicleType = (followingLive ? this.liveVehicleType : '') || latest?.vehicle_type || '';
        const mode = document.createElement('span');
        mode.className = armyType === 'air' ? 'army-status air-info' : 'army-status';
        const airLabel = this.mapKind === 'air' ? t('viewer.air_view_raw') : t('viewer.air_view');
        const surfaceLabel = this.battleType === 'naval' ? t('viewer.naval') : t('viewer.ground');
        mode.textContent = armyType === 'air' ? airLabel : surfaceLabel;
        const counts = t('viewer.stats', { positions: this.positionCount, pois: this.poiCount });
        statsEl.replaceChildren(counts, document.createElement('br'), mode);
        const vehicle = document.getElementById('own-vehicle-name');
        const name = vehicleType && !this.placeholderVehicles.includes(vehicleType)
            ? this._vehicleName(vehicleType) : t('viewer.vehicle_unavailable');
        if (vehicle.textContent !== name) {
            vehicle.textContent = name;
            vehicle.title = name;
        }
    }

    _categorize(pos) {
        const type = pos.type.toLowerCase();
        if (type === 'capture_zone') return 'capture_zone';
        if (type.includes('respawn') || type.includes('airfield')) return 'respawn';
        if (pos.icon === VIEW_STYLE.playerIcon) return 'player';
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
        // 空战图只画空中视角的原始坐标；纯空战图全部可画；海战水面图和录像还原的轨迹保留飞机。
        if (this.mapKind === 'air') return Boolean(pos.is_player_air_view);
        if (this.battleType === 'air') return true;
        const allowAircraft = this.battleType === 'naval' || this.replayTracks;
        return (allowAircraft || pos.type.toLowerCase() !== 'aircraft') && (!pos.is_player_air_view || pos.x_ground != null);
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
            // 录像单位自带玩家名与载具；8111 只知道自己的载具。
            const vehicle = pos.unit_vehicle ?? (pos.icon === VIEW_STYLE.playerIcon ? pos.vehicle_type : '');
            times.get(pos.timestamp).push({ ...point, icon: pos.icon, vehicle, name: pos.unit_name ?? '' });
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

    get isAtLatest() {
        return this.selectedTime === null;
    }

    getTimelineTime() {
        return this.selectedTime ?? this.getTimelineMax();
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
        const cutoff = this.getTimelineTime();
        const trailDuration = this.trail ? this.trail * 1000 : Math.max(1, cutoff);
        const { capture, respawn } = this._getPoiClusters(cutoff);
        this.poiCount = capture.length + respawn.length;

        const current = [];
        const deaths = [];
        const fades = new Map();
        let playerPoint = null;
        for (const { category, points } of this.tracks) {
            if (!this.filters[category]) continue;
            const [start, end] = this._visibleRange(points, cutoff);
            if (end < 0) continue;
            const point = points[end];
            const inTrail = start <= end;
            if (inTrail) {
                if (!fades.has(category)) fades.set(category, []);
                this._addTrack(fades.get(category), points, start, end, cutoff - trailDuration, trailDuration);
                if (cutoff - point.t <= VIEW_STYLE.aliveWindow) {
                    current.push({ category, point, previous: points[end - 1] });
                    if (category === 'player') playerPoint = point;
                }
            }
            const keepDeath = this.showAllFriendlyDeaths && (category === 'ally' || category === 'squad');
            if ((inTrail || keepDeath) && this._isDeath(category, points, end, cutoff)) {
                deaths.push({ category, point });
            }
        }

        if (this.followPlayer && playerPoint) {
            this.panX = this.viewWidth / 2 - playerPoint.x * w * this.zoom;
            this.panY = this.viewHeight / 2 - playerPoint.y * h * this.zoom;
            this._clampPan();
        }

        ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
        ctx.fillStyle = '#15191f';
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
        const mapDim = this.mapDim ?? VIEW_STYLE.mapDim;
        ctx.fillStyle = `rgba(0,0,0,${mapDim})`;
        ctx.fillRect(0, 0, w, h);

        this.markers = [];
        if (this.filters.capture_zone) {
            for (const point of capture) this._drawPoi(point, true);
        }
        if (this.filters.respawn) {
            for (const point of respawn) this._drawPoi(point, false);
        }
        this._drawFades(fades);
        for (const { category, point, previous } of current) this._drawCurrent(category, point, previous);
        for (const { category, point } of deaths) this._drawDeath(category, point);

        ctx.restore();
        this.onRender?.(this);
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

    // 按线段中点的时间淡化，旧轨迹保留少量不透明度。
    _fadeAlpha(previous, point, earliest, duration) {
        const progress = clamp(((previous.t + point.t) / 2 - earliest) / duration, [0, 1]);
        return 0.1 + progress * 0.9;
    }

    // 把轨迹的每一小段加入它所在档位的路径；levels[档位] 是该档所有线段合成的一条路径。
    _addTrack(levels, points, start, end, earliest, duration) {
        let lastLevel = -1;
        for (let i = start + 1; i <= end; i++) {
            if (this._isGap(points[i - 1], points[i])) {
                lastLevel = -1;
                continue;
            }
            const level = Math.round(this._fadeAlpha(points[i - 1], points[i], earliest, duration) * VIEW_STYLE.fadeLevels);
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
        const owner = this._nearestColor(point.color, VIEW_STYLE.ownerColors);
        const color = VIEW_STYLE.ownerColors[owner];
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
        if (isCapture) {
            this.markers.push({
                sx: x * this.zoom + this.panX, sy: y * this.zoom + this.panY, r: style.radius,
                kind: 'capture_zone', owner, timestamp: point.timestamp,
            });
        }
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
        this._registerMarker(point, x, y, size / 2);
    }

    _registerMarker(point, x, y, radius, extra = {}) {
        this.markers.push({
            sx: x * this.zoom + this.panX, sy: y * this.zoom + this.panY, r: radius * this.zoom,
            icon: point.icon, vehicle: point.vehicle, name: point.name, ...extra,
        });
    }

    // 返回屏幕坐标下最近的标记：单位标记优先于占领点圆圈，同级重合选最上层。
    _markerAt(sx, sy) {
        let bestUnit = null;
        let bestUnitDist = Infinity;
        let bestPoi = null;
        let bestPoiDist = Infinity;
        for (const marker of this.markers) {
            const distance = Math.hypot(marker.sx - sx, marker.sy - sy);
            if (distance > marker.r + VIEW_STYLE.hoverSlop) continue;
            if (marker.kind === 'capture_zone') {
                if (distance <= bestPoiDist) {
                    bestPoi = marker;
                    bestPoiDist = distance;
                }
            } else if (distance <= bestUnitDist) {
                bestUnit = marker;
                bestUnitDist = distance;
            }
        }
        return bestUnit ?? bestPoi;
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
        if (this.selectedEvent && point.t !== undefined && Math.abs(point.t - this.selectedEvent.timestamp) <= 2500) {
            const ctx = this.ctx;
            ctx.beginPath();
            ctx.arc(x, y, half * 2.2, 0, Math.PI * 2);
            ctx.strokeStyle = '#e5b82e';
            ctx.lineWidth = 2 / this.zoom;
            ctx.stroke();
        }
        this._registerMarker(point, x, y, half * Math.SQRT2, { deathTime: point.t });
    }

    _saveSettings() {
        window.Settings.save(VIEW_STYLE.settingsKey, {
            trail: this.trail, blipSize: this.blipSize, lineScale: this.lineScale, mapDim: this.mapDim,
            speed: this.speed, filters: this.filters, showAllFriendlyDeaths: this.showAllFriendlyDeaths,
            followFeed: this.followFeed, followPlayer: this.followPlayer,
            sidebarCollapsed: this.sidebarCollapsed, feedFilter: this.feedFilter,
        });
    }

    setFilters(filters) {
        Object.assign(this.filters, filters);
        this._saveSettings();
        this._render();
    }

    setShowAllFriendlyDeaths(enabled) {
        this.showAllFriendlyDeaths = enabled;
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

    setMapDim(dim) {
        this.mapDim = clamp(dim, VIEW_STYLE.mapDimRange);
        this._saveSettings();
        this._render();
    }

    setFollowPlayer(enabled) {
        this.followPlayer = Boolean(enabled);
        this._saveSettings();
        this.onFollowPlayerChange?.(this.followPlayer);
        this._render();
    }

    setSidebarCollapsed(collapsed) {
        this.sidebarCollapsed = Boolean(collapsed);
        this._saveSettings();
    }

    setFeedFilter(filter) {
        this.feedFilter = filter;
        this._saveSettings();
    }

    setSpeed(speed) {
        this.speed = nearestSpeed(speed);
        this._saveSettings();
    }

    stepSpeed(delta) {
        const speeds = VIEW_STYLE.speedOptions;
        const index = clamp(speeds.indexOf(this.speed) + delta, [0, speeds.length - 1]);
        this.setSpeed(speeds[index]);
        return this.speed;
    }

    stepTimeline(deltaMs) {
        const max = this.getTimelineMax();
        if (max === 0) return;
        this.pause();
        const next = clamp(this.getTimelineTime() + deltaMs, [0, max]);
        this.setTimelineTime(next);
    }

    setFollowFeed(enabled) {
        this.followFeed = enabled;
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
        if (this.isPlaying || this.getTimelineMax() === 0 || (this.isLive && this.isAtLatest)) return;
        if (this.isAtLatest) this.setTimelineTime(0);
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
        this.setTimelineTime(this.getTimelineTime() + dt * this.speed);
        if (this.isAtLatest) this.pause();
    }

    seekToEvent(event) {
        this.pause();
        this.setTimelineTime(event.timestamp, event);
    }

    setTimelineTime(time, event = null) {
        this.selectedEvent = event;
        this.selectedTime = event === null && time >= this.getTimelineMax() ? null : Math.max(0, time);
        this._render();
        this._updateStats();
    }

    returnToLive() {
        this.pause();
        this.setTimelineTime(this.getTimelineMax());
    }

    getTimelineMax() {
        return Math.max(this.maxTimestamp, this.events.at(-1)?.timestamp ?? 0);
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
