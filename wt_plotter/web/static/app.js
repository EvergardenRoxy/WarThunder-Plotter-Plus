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
    const timeline = document.getElementById('timeline-slider');
    const currentTime = document.getElementById('timeline-current');
    const maxTime = document.getElementById('timeline-max');
    const timelineState = document.getElementById('timeline-state');
    const timelineDelay = document.getElementById('timeline-delay');
    const timelineEvents = document.getElementById('timeline-events');
    const axisTicks = document.querySelectorAll('[data-axis-tick]');
    const playButton = document.getElementById('timeline-play');
    const liveButton = document.getElementById('timeline-live');
    const feed = document.getElementById('event-feed');
    const feedCount = document.getElementById('feed-count');
    const feedEmpty = document.getElementById('feed-empty');
    const followFeed = document.getElementById('follow-feed');
    const eventRows = new Map();
    let activeEvent;
    let followedEvent;
    const syncFeed = (view, time) => {
        const index = window.Tracks.lastIndexAtMost(view.events, time, event => event.timestamp);
        const event = view.selectedEvent ?? view.events[index];
        if (event !== activeEvent) {
            eventRows.get(activeEvent)?.removeAttribute('aria-current');
            eventRows.get(event)?.setAttribute('aria-current', 'true');
            activeEvent = event;
        }
        const anchor = event ?? view.events[0];
        if (view.followFeed && anchor && anchor !== followedEvent) {
            feed.scrollTop = eventRows.get(anchor).parentElement.offsetTop;
            followedEvent = anchor;
        }
    };
    const mapKindControl = document.getElementById('map-kind');
    const mapKindButtons = mapKindControl.querySelectorAll('[data-map-kind]');
    const mapTitle = document.getElementById('match-map-title');
    const modeTitle = document.getElementById('match-mode-title');
    const mapLabel = document.getElementById('match-map-label');
    const airMapLabel = document.getElementById('match-air-map-label');
    const markMapKind = view => {
        for (const button of mapKindButtons) {
            button.setAttribute('aria-pressed', String(button.dataset.mapKind === view.mapKind));
        }
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
            const slots = new Set(view.events.map(event => slot(event.timestamp)));
            for (const position of slots) {
                const marker = document.createElement('span');
                marker.style.left = position + '%';
                marker.classList.toggle('selected', selected !== undefined && position === slot(selected));
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
            playButton.disabled = max === 0 || (view.isLive && view.isAtLatest);
            if (liveButton) liveButton.disabled = view.isAtLatest;
        },
        onEvents(events, view) {
            feedCount.textContent = t('viewer.feed_count', { count: view.events.length });
            feedEmpty.remove();
            const firstRow = feed.firstElementChild;
            const previousTop = firstRow?.offsetTop;
            const scrollTop = feed.scrollTop;
            const items = document.createDocumentFragment();
            for (const event of events) {
                const item = document.createElement('li');
                const button = document.createElement('button');
                button.className = 'event-seek';
                button.type = 'button';
                const time = document.createElement('time');
                time.textContent = view.formatTime(event.timestamp);
                const message = document.createElement('span');
                message.textContent = event.msg;
                button.append(time, message);
                button.addEventListener('click', () => view.seekToEvent(event));
                eventRows.set(event, button);
                item.append(button);
                items.prepend(item);
            }
            feed.prepend(items);
            followedEvent = undefined;
            if (!view.followFeed && firstRow) {
                // 新战报插在顶部时，保持正在阅读的条目原位。
                feed.scrollTop = scrollTop + firstRow.offsetTop - previousTop;
            }
        },
        onPlayStateChange(isPlaying) {
            playButton.textContent = isPlaying ? t('viewer.pause') : t('viewer.play');
        },
        onMapUpdate(view, match) {
            mapKindControl.hidden = !match.air_map;
            airMapLabel.hidden = !match.air_map;
            for (const [element, text] of [
                [mapTitle, match.map_name], [modeTitle, match.mode_label],
                [mapLabel, match.map_label], [airMapLabel, match.air_map_label],
            ]) {
                if (element.textContent !== text) element.textContent = text;
            }
            markMapKind(view);
        }
    });

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
    const trail = document.getElementById('trail-length');
    for (const seconds of VIEW_STYLE.trailOptions) {
        const label = seconds ? t('viewer.trail_seconds', { n: seconds }) : t('viewer.trail_all');
        trail.add(new Option(label, String(seconds), false, seconds === viewer.trail));
    }
    trail.addEventListener('change', () => viewer.setTrail(Number(trail.value)));

    const speeds = VIEW_STYLE.speedOptions;
    document.getElementById('speed-slider').max = speeds.length - 1;
    bindSlider(
        'speed-slider', speeds.indexOf(viewer.speed), index => viewer.setSpeed(speeds[index]),
        index => t('viewer.speed_value', { n: speeds[index] }),
    );

    const togglePlayback = () => {
        if (viewer.isPlaying) viewer.pause();
        else viewer.play();
    };
    playButton.addEventListener('click', togglePlayback);
    document.addEventListener('keydown', event => {
        if (event.code !== 'Space' || event.defaultPrevented || event.ctrlKey || event.altKey || event.metaKey) return;
        if (event.target !== timeline && event.target.closest('button, input, select, textarea, summary, a[href], [contenteditable]')) return;
        event.preventDefault();
        if (!event.repeat) togglePlayback();
    });
    timeline.addEventListener('input', () => {
        viewer.pause();
        viewer.setTimelineTime(timeline.valueAsNumber);
    });
    liveButton?.addEventListener('click', () => viewer.returnToLive());
}
