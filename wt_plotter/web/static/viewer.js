
class MatchViewer {
    constructor(canvasId, matchId, { isLive = false, isAirMap = false, pollInterval = 500, onRender } = {}) {
        this.canvas = document.getElementById(canvasId);
        this.ctx = this.canvas.getContext('2d');
        this.matchId = matchId;
        this.isLive = isLive;
        this.isAirMap = isAirMap;
        this.pollInterval = pollInterval;
        this.onRender = onRender;
        this.positions = [];
        this.pois = [];
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
        this.filters = {
            player: true,
            squad: true,
            ally: true,
            enemy: true,
            capture_zone: true,
            respawn: true,
            other: true
        };
        this.blipSize = 1.5;
        this.timelinePosition = 1.0;
        this.maxTimestamp = 0;
        this._loadMap();
        this._setupInteractions();
        if (this.isLive) {
            this._startPolling();
        } else {
            this._loadPositions();
        }
        window.addEventListener('resize', () => this._resize());
        requestAnimationFrame(() => {
            this._resize();
            this._render();
        });
    }

    _resize() {
        const container = this.canvas.parentElement;
        const size = Math.min(container.clientWidth, container.clientHeight, 1500);
        this.canvas.width = size;
        this.canvas.height = size;
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
        const w = this.canvas.width;
        const h = this.canvas.height;
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
            const cx = this.canvas.width / 2;
            const cy = this.canvas.height / 2;
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
            const cx = this.canvas.width / 2;
            const cy = this.canvas.height / 2;
            const zoomRatio = newZoom / this.zoom;
            this.panX = cx - (cx - this.panX) * zoomRatio;
            this.panY = cy - (cy - this.panY) * zoomRatio;
            this.zoom = newZoom;
            this._clampPan();
            this._render();
            this._updateZoomDisplay();
        }
    }

    async _loadMap() {
        const img = new Image();
        img.onload = () => {
            this.mapImage = img;
            this._render();
        };
        img.onerror = () => {
            console.warn('Failed to load map image');
            this._render();
        };
        img.src = `/api/match/${this.matchId}/map.png`;
    }

    async _loadPositions() {
        try {
            const resp = await fetch(`/api/match/${this.matchId}/positions?since=${this.lastTimestamp}`);
            const data = await resp.json();
            const ticks = data.ticks || [];
            const positions = data.positions || [];

            if (positions.length > 0) {
                const tickMap = new Map();
                for (const tick of ticks) {
                    tickMap.set(tick.id, tick);
                }
                const processed = positions.map(pos => {
                    const tick = tickMap.get(pos.tick_id);
                    if (!tick) {
                        return null;
                    }
                    const merged = {
                        ...pos,
                        timestamp: tick.timestamp,
                        army_type: tick.army_type,
                        vehicle_type: tick.vehicle_type,
                        is_player_air: tick.is_player_air,
                        is_player_air_view: tick.is_player_air_view
                    };
                    if (merged.x_ground !== null && merged.x_ground !== undefined &&
                        merged.y_ground !== null && merged.y_ground !== undefined) {
                        return {
                            ...merged,
                            x: merged.x_ground,
                            y: merged.y_ground,
                            x_original: merged.x,
                            y_original: merged.y
                        };
                    }
                    return merged;
                }).filter(Boolean);
                // 逐条累计最大时间戳；整场位置太多，不能展开成函数参数。
                let maxTs = -Infinity;
                for (const pos of processed) {
                    if (pos.is_poi) {
                        this.pois.push(pos);
                    } else {
                        this.positions.push(pos);
                    }
                    if (pos.timestamp > maxTs) maxTs = pos.timestamp;
                }
                if (maxTs >= this.lastTimestamp) {
                    this.lastTimestamp = maxTs + 1;
                }
                if (maxTs > this.maxTimestamp) {
                    this.maxTimestamp = maxTs;
                }

                this._render();
            }
            this._updateStats();
        } catch (e) {
            console.error('Failed to load positions:', e);
            this._updateStats();
        }
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
        if (statsEl) {
            const total = this.positions.length;
            const poiCount = new Set(this.pois.map(p => `${p.x.toFixed(3)},${p.y.toFixed(3)}`)).size;
            let armyType = 'tank';
            let vehicleType = '';

            console.debug(`Updating stats. isLive: ${this.isLive}, timelinePosition: ${this.timelinePosition}, positions count: ${this.positions.length}`);
            if (this.isLive) {
                console.debug(`Live army type: ${this.liveArmyType}, vehicle type: ${this.liveVehicleType}`);
                armyType = this.liveArmyType || 'tank';
                vehicleType = this.liveVehicleType || '';
                if ((!vehicleType || !armyType) && this.positions.length > 0) {
                    const latest = this.positions[this.positions.length - 1];
                    armyType = armyType || latest.army_type || 'tank';
                    vehicleType = vehicleType || latest.vehicle_type || '';
                }
            } else if (this.positions.length > 0) {
                if (this.timelinePosition >= 1.0) {
                    armyType = this.positions[this.positions.length - 1].army_type || 'tank';
                    vehicleType = this.positions[this.positions.length - 1].vehicle_type || '';
                } else {
                    const cutoffTime = this.maxTimestamp * this.timelinePosition;
                    for (let i = this.positions.length - 1; i >= 0; i--) {
                        if (this.positions[i].timestamp <= cutoffTime) {
                            armyType = this.positions[i].army_type || 'tank';
                            vehicleType = this.positions[i].vehicle_type || '';
                            break;
                        }
                    }
                }
            }
            let vehicleName = '';
            if (vehicleType) {
                const parts = vehicleType.split('/');
                vehicleName = parts[parts.length - 1].replace(/_/g, ' ');
            }

            const mode = document.createElement('span');
            mode.className = armyType === 'air' ? 'army-status air-info' : 'army-status';
            mode.textContent = armyType === 'air' ? t('viewer.air_view') : t('viewer.ground');
            statsEl.replaceChildren(t('viewer.stats', { positions: total, pois: poiCount }), document.createElement('br'), mode);
            if (vehicleName) {
                const vehicle = document.createElement('span');
                vehicle.className = 'vehicle-name';
                vehicle.textContent = vehicleName;
                statsEl.append(document.createElement('br'), vehicle);
            }
        }
    }

    _categorize(pos) {
        const type = pos.type.toLowerCase();
        const icon = (pos.icon || '').toLowerCase();
        const color = (pos.color || '#FFFFFF').toUpperCase();
        if (type === 'capture_zone') return 'capture_zone';
        if (type.includes('respawn') || type.includes('airfield')) return 'respawn';
        const rgb = this._parseColor(color);
        if (rgb) {
            const [r, g, b] = rgb;
            if (r > 200 && g > 150 && b < 100) {
                return 'player';
            }
            if (g > 180 && r < 150 && b < 150) {
                return 'squad';
            }
            if (r > 200 && g < 100 && b < 100) {
                return 'enemy';
            }
            if (b > 200 && r < 100) {
                return 'ally';
            }
        }
        if (icon === 'player') {
            return 'player';
        }

        return 'other';
    }

    _parseColor(hex) {
        if (!hex) return null;
        hex = hex.replace('#', '');
        if (hex.length === 3) {
            hex = hex.split('').map(c => c + c).join('');
        }
        if (hex.length !== 6) return null;

        const r = parseInt(hex.slice(0, 2), 16);
        const g = parseInt(hex.slice(2, 4), 16);
        const b = parseInt(hex.slice(4, 6), 16);

        if (isNaN(r) || isNaN(g) || isNaN(b)) return null;
        return [r, g, b];
    }

    _shouldShow(pos) {
        // 空战地图上的坐标本来就属于这张图，全部显示。
        // 其它比赛里隐藏飞机，以及没有换算成地面坐标的空中视角位置。
        if (!this.isAirMap) {
            const isAirType = (pos.type || '').toLowerCase() === 'aircraft';
            if (isAirType) return false;
            const isAirView = pos.is_player_air_view || pos.is_player_air;
            if (isAirView && (pos.x_ground === null || pos.x_ground === undefined)) {
                return false;
            }
        }

        const cat = this._categorize(pos);
        if (this.filters[cat] === false) return false;
        if (!this.isLive && !pos.is_poi && this.timelinePosition < 1.0) {
            const cutoffTime = this.maxTimestamp * this.timelinePosition;
            if (pos.timestamp > cutoffTime) return false;
        }

        return true;
    }

    _getCurrentPois() {
        if (this.isLive || this.timelinePosition >= 1.0) {
            const poiMap = new Map();
            for (const pos of this.pois) {
                const key = `${pos.x.toFixed(3)},${pos.y.toFixed(3)}`;
                if (!poiMap.has(key) || pos.timestamp > poiMap.get(key).timestamp) {
                    poiMap.set(key, pos);
                }
            }
            return Array.from(poiMap.values());
        } else {
            const cutoffTime = this.maxTimestamp * this.timelinePosition;
            const poiMap = new Map();
            for (const pos of this.pois) {
                if (pos.timestamp <= cutoffTime) {
                    const key = `${pos.x.toFixed(3)},${pos.y.toFixed(3)}`;
                    if (!poiMap.has(key) || pos.timestamp > poiMap.get(key).timestamp) {
                        poiMap.set(key, pos);
                    }
                }
            }
            return Array.from(poiMap.values());
        }
    }

    _render() {
        const ctx = this.ctx;
        const w = this.canvas.width;
        const h = this.canvas.height;
        ctx.fillStyle = '#1a1a1a';
        ctx.fillRect(0, 0, w, h);
        ctx.save();
        ctx.translate(this.panX, this.panY);
        ctx.scale(this.zoom, this.zoom);
        if (this.mapImage) {
            ctx.drawImage(this.mapImage, 0, 0, w, h);
        } else {
            ctx.strokeStyle = '#333';
            ctx.lineWidth = 1 / this.zoom;
            for (let i = 0; i <= 10; i++) {
                const p = (i / 10) * w;
                ctx.beginPath();
                ctx.moveTo(p, 0);
                ctx.lineTo(p, h);
                ctx.stroke();
                ctx.beginPath();
                ctx.moveTo(0, p);
                ctx.lineTo(w, p);
                ctx.stroke();
            }
        }
        const currentPois = this._getCurrentPois();
        for (const pos of currentPois) {
            if (this._shouldShow(pos)) {
                this._drawPOI(pos, w, h);
            }
        }
        for (const pos of this.positions) {
            if (this._shouldShow(pos)) {
                this._drawPosition(pos, w, h);
            }
        }
        ctx.restore();
        this.onRender?.(this);
    }

    _drawPOI(pos, w, h) {
        const ctx = this.ctx;
        const x = pos.x * w;
        const y = pos.y * h;
        const type = pos.type.toLowerCase();

        if (type === 'capture_zone') {
            ctx.beginPath();
            ctx.arc(x, y, 20, 0, Math.PI * 2);
            ctx.fillStyle = this._hexToRgba(pos.color, 0.3);
            ctx.fill();
            ctx.strokeStyle = pos.color;
            ctx.lineWidth = 2;
            ctx.stroke();
        } else {
            ctx.beginPath();
            ctx.moveTo(x, y - 3);
            ctx.lineTo(x - 2, y + 1);
            ctx.lineTo(x + 2, y + 1);
            ctx.closePath();
            ctx.fillStyle = this._hexToRgba(pos.color, 0.3);
            ctx.fill();
            ctx.strokeStyle = pos.color;
            ctx.lineWidth = 1;
            ctx.stroke();
        }
    }

    _drawPosition(pos, w, h) {
        const ctx = this.ctx;
        const x = pos.x * w;
        const y = pos.y * h;
        let size = this.blipSize;
        let alpha = 1.0;
        ctx.beginPath();
        ctx.arc(x, y, size, 0, Math.PI * 2);
        ctx.fillStyle = this._hexToRgba(pos.color, alpha);
        ctx.fill();
    }

    _hexToRgba(hex, alpha) {
        if (!hex || hex === '#FFFFFF' || hex === '#ffffff') {
            return `rgba(255, 255, 255, ${alpha})`;
        }
        const colors = {
            'blue': '#4444ff',
            'red': '#ff4444',
            'green': '#44ff44',
            'yellow': '#ffff44',
            'white': '#ffffff',
            'gray': '#888888'
        };
        if (colors[hex.toLowerCase()]) {
            hex = colors[hex.toLowerCase()];
        }
        if (hex.startsWith('#')) {
            hex = hex.slice(1);
        }
        if (hex.length === 3) {
            hex = hex.split('').map(c => c + c).join('');
        }

        const r = parseInt(hex.slice(0, 2), 16);
        const g = parseInt(hex.slice(2, 4), 16);
        const b = parseInt(hex.slice(4, 6), 16);
        return `rgba(${isNaN(r) ? 255 : r}, ${isNaN(g) ? 255 : g}, ${isNaN(b) ? 255 : b}, ${alpha})`;
    }

    setFilter(category, enabled) {
        this.filters[category] = enabled;
        this._render();
    }

    setBlipSize(size) {
        this.blipSize = Math.max(0.5, Math.min(3, size));
        this._render();
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
        this._stopPolling();
    }
}
window.MatchViewer = MatchViewer;
