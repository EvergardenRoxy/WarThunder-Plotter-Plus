document.getElementById('quit-app').addEventListener('click', async () => {
    if (!window.confirm(t('confirm.quit'))) return;
    try {
        const response = await fetch('/shutdown', { method: 'POST' });
        if (!response.ok) throw new Error(response.status);
        window.close();
    } catch {
        window.alert(t('error.request_failed'));
    }
});

const languageSelect = document.getElementById('language-select');
languageSelect.addEventListener('change', async () => {
    try {
        const response = await fetch('/api/language', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ language: languageSelect.value })
        });
        if (!response.ok) throw new Error(response.status);
        window.location.reload();
    } catch {
        languageSelect.value = document.documentElement.lang;
        window.alert(t('error.request_failed'));
    }
});

for (const button of document.querySelectorAll('[data-delete-url]')) {
    button.addEventListener('click', async () => {
        if (!window.confirm(t('confirm.delete_match', { name: button.dataset.mapName }))) return;
        try {
            const response = await fetch(button.dataset.deleteUrl, { method: 'DELETE' });
            if (response.ok) {
                window.location.reload();
                return;
            }
            const data = await response.json();
            window.alert(t(`error.${data.error}`));
        } catch {
            window.alert(t('error.request_failed'));
        }
    });
}

const matchFilterForm = document.querySelector('.match-filters');
if (matchFilterForm) {
    for (const id of ['match-date', 'match-mode']) {
        document.getElementById(id).addEventListener('change', () => matchFilterForm.requestSubmit());
    }
    for (const img of document.querySelectorAll('.match-thumb')) {
        img.addEventListener('error', () => img.remove());
    }
}

const captureStopped = document.getElementById('capture-stopped');
async function pollCaptureStatus() {
    try {
        const response = await fetch('/api/status');
        const status = await response.json();
        captureStopped.hidden = status.capturing;
        if (document.getElementById('waiting-for-match') && status.active_match_id !== null) {
            window.location.reload();
        }
    } catch (error) {
        console.error('Failed to check capture status:', error);
    }
}

if (document.getElementById('waiting-for-match')) {
    pollCaptureStatus();
    setInterval(pollCaptureStatus, 2000);
}

const mapCanvas = document.getElementById('mapCanvas');
if (mapCanvas) {
    const viewerRoot = document.querySelector('.viewer');
    const toggleSidebarButton = document.getElementById('toggle-sidebar');
    const followPlayerButton = document.getElementById('follow-player');
    const timeline = document.getElementById('timeline-slider');
    const currentTime = document.getElementById('timeline-current');
    const maxTime = document.getElementById('timeline-max');
    const timelineState = document.getElementById('timeline-state');
    const timelineDelay = document.getElementById('timeline-delay');
    const timelineEvents = document.getElementById('timeline-events');
    const axisTicks = document.querySelectorAll('[data-axis-tick]');
    const playButton = document.getElementById('timeline-play');
    const liveButton = document.getElementById('timeline-live');
    const speedDown = document.getElementById('speed-down');
    const speedSelect = document.getElementById('speed-select');
    const speedUp = document.getElementById('speed-up');
    const sortieBar = document.getElementById('sortie-bar');
    const sortieList = document.getElementById('sortie-list');
    const feed = document.getElementById('event-feed');
    const feedCount = document.getElementById('feed-count');
    const feedEmpty = document.getElementById('feed-empty');
    const followFeed = document.getElementById('follow-feed');
    const feedFilterButtons = document.querySelectorAll('[data-feed-filter]');
    const eventRows = new Map();
    let activeEvent;
    let followedEvent;
    let lastTickCount = -1;
    let sorties = [];
    let sortieButtons = [];

    const updateFeedFilter = (view) => {
        const filter = view.feedFilter;
        let shown = 0;
        for (const row of eventRows.values()) {
            const visible = window.MatchUtils.matchesFeedFilter(row.kind, filter);
            row.item.hidden = !visible;
            if (visible) shown++;
        }
        for (const button of feedFilterButtons) {
            button.setAttribute('aria-pressed', String(button.dataset.feedFilter === filter));
        }
        const total = view.events.length;
        if (total === 0) {
            feedCount.textContent = '';
            feedEmpty.textContent = t('viewer.feed_empty');
            if (!feedEmpty.isConnected) feed.append(feedEmpty);
        } else if (shown === 0) {
            feedCount.textContent = t('viewer.feed_count_filtered', { shown, total });
            feedEmpty.textContent = t('viewer.feed_empty_filtered');
            if (!feedEmpty.isConnected) feed.append(feedEmpty);
        } else {
            feedCount.textContent = filter === 'all'
                ? t('viewer.feed_count', { count: total })
                : t('viewer.feed_count_filtered', { shown, total });
            feedEmpty.remove();
        }
    };

    const syncFeed = (view, time) => {
        const index = window.Tracks.lastIndexAtMost(view.events, time, event => event.timestamp);
        const event = view.selectedEvent ?? view.events[index];
        if (event !== activeEvent) {
            eventRows.get(activeEvent)?.button.removeAttribute('aria-current');
            eventRows.get(event)?.button.setAttribute('aria-current', 'true');
            activeEvent = event;
        }
        const anchor = event ?? view.events[0];
        const anchorRow = eventRows.get(anchor);
        if (view.followFeed && anchorRow && !anchorRow.item.hidden && anchor !== followedEvent) {
            feed.scrollTop = anchorRow.item.offsetTop;
            followedEvent = anchor;
        }
    };

    const syncSorties = (view, time) => {
        if (view.ticks.length !== lastTickCount) {
            lastTickCount = view.ticks.length;
            const next = window.MatchUtils.extractSorties(view.ticks, view.placeholderVehicles, view.playerTickIds);
            if (next.length !== sorties.length || next.some((s, i) => s.timestamp !== sorties[i].timestamp || s.vehicle !== sorties[i].vehicle)) {
                sorties = next;
                sortieButtons = sorties.map(sortie => {
                    const button = document.createElement('button');
                    button.type = 'button';
                    button.className = 'sortie-chip';
                    const timeLabel = view.formatTime(sortie.timestamp);
                    button.title = t('viewer.sortie_seek', { vehicle: sortie.vehicle, time: timeLabel });
                    const timeEl = document.createElement('time');
                    timeEl.textContent = timeLabel;
                    const nameEl = document.createElement('span');
                    nameEl.textContent = sortie.vehicle;
                    button.append(timeEl, nameEl);
                    button.addEventListener('click', () => {
                        view.pause();
                        view.setTimelineTime(sortie.timestamp);
                    });
                    return button;
                });
                sortieList.replaceChildren(...sortieButtons);
                sortieBar.hidden = sorties.length === 0;
            }
        }
        if (sorties.length > 0) {
            const activeIndex = window.Tracks.lastIndexAtMost(sorties, time, sortie => sortie.timestamp);
            sortieButtons.forEach((button, index) => {
                if (index === activeIndex) button.setAttribute('aria-current', 'true');
                else button.removeAttribute('aria-current');
            });
        }
    };

    const mapKindControl = document.getElementById('map-kind');
    const mapKindButtons = mapKindControl.querySelectorAll('[data-map-kind]');
    const nukeBadge = document.getElementById('nuke-badge');
    const mapTitle = document.getElementById('match-map-title');
    const modeTitle = document.getElementById('match-mode-title');
    const mapLabel = document.getElementById('match-map-label');
    const airMapLabel = document.getElementById('match-air-map-label');
    const markMapKind = view => {
        for (const button of mapKindButtons) {
            button.setAttribute('aria-pressed', String(button.dataset.mapKind === view.mapKind));
        }
    };
    const syncFollowPlayer = enabled => {
        followPlayerButton.setAttribute('aria-pressed', String(enabled));
    };
    let timelineScaleKey;
    const markTimeline = (view, max) => {
        const selected = view.selectedEvent?.timestamp;
        const key = [max, view.events.length, selected].join(':');
        if (key === timelineScaleKey) return;
        timelineScaleKey = key;
        axisTicks.forEach((tick, i) => {
            tick.textContent = view.formatTime(max * i / (axisTicks.length - 1));
        });
        const markers = document.createDocumentFragment();
        if (max > 0) {
            const slot = time => Math.round(100 * time / max);
            const slots = new Map();
            for (const event of view.events) {
                const pos = slot(event.timestamp);
                const kind = window.MatchUtils.classifyEvent(event.msg);
                const prev = slots.get(pos);
                if (!prev || window.MatchUtils.eventPriority(kind) > window.MatchUtils.eventPriority(prev)) {
                    slots.set(pos, kind);
                }
            }
            const selectedSlot = selected !== undefined ? slot(selected) : -1;
            for (const [position, kind] of slots) {
                const marker = document.createElement('span');
                marker.style.left = position + '%';
                marker.className = `kind-${kind}`;
                if (position === selectedSlot) marker.classList.add('selected');
                markers.append(marker);
            }
        }
        timelineEvents.replaceChildren(markers);
    };
    const viewer = new MatchViewer(mapCanvas.id, Number(mapCanvas.dataset.matchId), {
        isLive: mapCanvas.dataset.live === 'true',
        battleType: mapCanvas.dataset.battleType,
        mapKind: mapCanvas.dataset.defaultMap,
        placeholderVehicles: JSON.parse(mapCanvas.dataset.placeholderVehicles),
        pollInterval: 500,
        onFollowPlayerChange: syncFollowPlayer,
        onRender(view) {
            const max = view.getTimelineMax();
            const time = view.getTimelineTime();
            const label = view.formatTime(time);
            timeline.max = max;
            timeline.value = time;
            timeline.disabled = max === 0;
            timeline.setAttribute('aria-valuetext', label);
            currentTime.textContent = label;
            maxTime.textContent = view.formatTime(max);
            const mode = view.isLive ? (view.isAtLatest ? 'live' : 'rewind') : 'replay';
            timelineState.textContent = t(`viewer.timeline_${mode}`);
            timelineDelay.textContent = mode === 'rewind'
                ? t('viewer.timeline_delay', { time: view.formatTime(max - time) }) : '';
            markTimeline(view, max);
            syncFeed(view, time);
            syncSorties(view, time);
            playButton.disabled = max === 0 || (view.isLive && view.isAtLatest);
            if (liveButton) liveButton.disabled = view.isAtLatest;
        },
        onEvents(events, view) {
            const firstRow = feed.firstElementChild;
            const previousTop = firstRow?.offsetTop;
            const scrollTop = feed.scrollTop;
            const items = document.createDocumentFragment();
            for (const event of events) {
                const kind = window.MatchUtils.classifyEvent(event.msg);
                const item = document.createElement('li');
                item.dataset.eventKind = kind;
                const button = document.createElement('button');
                button.className = 'event-seek';
                button.type = 'button';
                const time = document.createElement('time');
                time.textContent = view.formatTime(event.timestamp);
                const message = document.createElement('span');
                message.textContent = event.msg;
                button.append(time, message);
                button.addEventListener('click', () => view.seekToEvent(event));
                eventRows.set(event, { button, item, kind });
                item.append(button);
                items.prepend(item);
            }
            feed.prepend(items);
            updateFeedFilter(view);
            followedEvent = undefined;
            if (!view.followFeed && firstRow && firstRow !== feedEmpty) {
                // 新战报插在顶部时，保持正在阅读的条目原位。
                feed.scrollTop = scrollTop + firstRow.offsetTop - previousTop;
            }
        },
        onPlayStateChange(isPlaying) {
            playButton.textContent = isPlaying ? t('viewer.pause') : t('viewer.play');
        },
        onMapUpdate(view, match) {
            mapKindControl.hidden = !(match.air_map || match.has_air_view);
            airMapLabel.hidden = !match.air_map;
            nukeBadge.hidden = !match.nuke_detected;
            for (const [element, text] of [
                [mapTitle, match.map_name], [modeTitle, match.mode_label],
                [mapLabel, match.map_label], [airMapLabel, match.air_map_label],
            ]) {
                if (element.textContent !== text) element.textContent = text;
            }
            markMapKind(view);
        }
    });

    const applySidebar = collapsed => {
        viewerRoot.classList.toggle('sidebar-collapsed', collapsed);
        toggleSidebarButton.setAttribute('aria-pressed', String(!collapsed));
        toggleSidebarButton.title = t(collapsed ? 'viewer.show_sidebar' : 'viewer.hide_sidebar');
    };
    const toggleSidebar = () => {
        viewer.setSidebarCollapsed(!viewer.sidebarCollapsed);
        applySidebar(viewer.sidebarCollapsed);
    };
    applySidebar(viewer.sidebarCollapsed);
    toggleSidebarButton.addEventListener('click', toggleSidebar);

    syncFollowPlayer(viewer.followPlayer);
    followPlayerButton.addEventListener('click', () => viewer.setFollowPlayer(!viewer.followPlayer));

    for (const button of mapKindButtons) {
        button.addEventListener('click', () => {
            viewer.setMapKind(button.dataset.mapKind);
            markMapKind(viewer);
        });
    }

    document.getElementById('zoom-in').addEventListener('click', () => viewer.zoomIn());
    document.getElementById('zoom-out').addEventListener('click', () => viewer.zoomOut());
    document.getElementById('zoom-reset').addEventListener('click', () => viewer.resetView());
    const filterInputs = document.querySelectorAll('[data-filter]');
    const presetButtons = document.querySelectorAll('[data-filter-preset]');
    const presets = { all: ['player', 'squad', 'ally', 'enemy', 'other'], squad: ['player', 'squad'] };
    const syncFilters = () => {
        for (const input of filterInputs) input.checked = viewer.filters[input.dataset.filter];
        for (const button of presetButtons) {
            const enabled = presets[button.dataset.filterPreset];
            const selected = presets.all.every(category => viewer.filters[category] === enabled.includes(category));
            button.setAttribute('aria-pressed', String(selected));
        }
    };
    for (const input of filterInputs) {
        input.addEventListener('change', () => {
            viewer.setFilters({ [input.dataset.filter]: input.checked });
            syncFilters();
        });
    }
    for (const button of presetButtons) {
        button.addEventListener('click', () => {
            const enabled = presets[button.dataset.filterPreset];
            viewer.setFilters(Object.fromEntries(presets.all.map(category => [category, enabled.includes(category)])));
            syncFilters();
        });
    }
    syncFilters();
    const friendlyDeaths = document.getElementById('show-all-friendly-deaths');
    friendlyDeaths.checked = viewer.showAllFriendlyDeaths;
    friendlyDeaths.addEventListener('change', () => viewer.setShowAllFriendlyDeaths(friendlyDeaths.checked));
    followFeed.checked = viewer.followFeed;
    followFeed.addEventListener('change', () => {
        viewer.setFollowFeed(followFeed.checked);
        followedEvent = undefined;
        syncFeed(viewer, viewer.getTimelineTime());
    });
    for (const button of feedFilterButtons) {
        button.addEventListener('click', () => {
            viewer.setFeedFilter(button.dataset.feedFilter);
            updateFeedFilter(viewer);
            followedEvent = undefined;
            syncFeed(viewer, viewer.getTimelineTime());
        });
    }
    updateFeedFilter(viewer);

    const bindSlider = (id, value, setter, format = text => text) => {
        const slider = document.getElementById(id);
        const label = document.getElementById(`${id}-value`);
        const updateLabel = () => {
            const text = format(slider.value);
            label.textContent = text;
            slider.setAttribute('aria-valuetext', text);
        };
        slider.value = value;
        updateLabel();
        slider.addEventListener('input', () => {
            setter(Number(slider.value));
            updateLabel();
        });
    };
    bindSlider('blip-size', viewer.blipSize, value => viewer.setBlipSize(value));
    bindSlider('line-scale', viewer.lineScale, value => viewer.setLineScale(value));
    bindSlider('map-dim', viewer.mapDim, value => viewer.setMapDim(value), value => `${Math.round(Number(value) * 100)}%`);
    const trail = document.getElementById('trail-length');
    for (const seconds of VIEW_STYLE.trailOptions) {
        const label = seconds ? t('viewer.trail_seconds', { n: seconds }) : t('viewer.trail_all');
        trail.add(new Option(label, String(seconds), false, seconds === viewer.trail));
    }
    trail.addEventListener('change', () => viewer.setTrail(Number(trail.value)));

    const speeds = VIEW_STYLE.speedOptions;
    for (const speed of speeds) {
        speedSelect.add(new Option(t('viewer.speed_value', { n: speed }), String(speed), false, speed === viewer.speed));
    }
    const syncSpeed = () => {
        speedSelect.value = String(viewer.speed);
        speedDown.disabled = viewer.speed === speeds[0];
        speedUp.disabled = viewer.speed === speeds.at(-1);
    };
    syncSpeed();
    speedSelect.addEventListener('change', () => {
        viewer.setSpeed(Number(speedSelect.value));
        syncSpeed();
    });
    speedDown.addEventListener('click', () => { viewer.stepSpeed(-1); syncSpeed(); });
    speedUp.addEventListener('click', () => { viewer.stepSpeed(1); syncSpeed(); });

    const togglePlayback = () => {
        if (viewer.isPlaying) viewer.pause();
        else viewer.play();
    };
    playButton.addEventListener('click', togglePlayback);
    document.addEventListener('keydown', event => {
        if (event.defaultPrevented || event.ctrlKey || event.altKey || event.metaKey) return;
        const interactive = event.target.closest('input, select, textarea, [contenteditable]');
        if (event.code === 'Space') {
            if (event.target !== timeline && event.target.closest('button, input, select, textarea, summary, a[href], [contenteditable]')) return;
            event.preventDefault();
            if (!event.repeat) togglePlayback();
            return;
        }
        if (interactive && event.target !== timeline) return;
        if (event.code === 'ArrowLeft' || event.code === 'ArrowRight') {
            event.preventDefault();
            const step = event.shiftKey ? 15000 : 5000;
            viewer.stepTimeline(event.code === 'ArrowLeft' ? -step : step);
        } else if (event.code === 'BracketLeft' || event.code === 'BracketRight') {
            event.preventDefault();
            viewer.stepSpeed(event.code === 'BracketLeft' ? -1 : 1);
            syncSpeed();
        } else if (event.code === 'KeyL' && liveButton && !liveButton.disabled) {
            event.preventDefault();
            viewer.returnToLive();
        } else if (event.code === 'KeyR' || event.code === 'Digit0') {
            event.preventDefault();
            viewer.resetView();
        } else if (event.code === 'KeyF' && !event.repeat) {
            event.preventDefault();
            viewer.setFollowPlayer(!viewer.followPlayer);
        } else if (event.code === 'KeyB' && !event.repeat) {
            event.preventDefault();
            toggleSidebar();
        }
    });
    timeline.addEventListener('input', () => {
        viewer.pause();
        viewer.setTimelineTime(timeline.valueAsNumber);
    });
    liveButton?.addEventListener('click', () => viewer.returnToLive());
}
