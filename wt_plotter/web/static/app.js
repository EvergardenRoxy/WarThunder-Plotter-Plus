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
    const playButton = document.getElementById('timeline-play');
    const viewer = new MatchViewer(mapCanvas.id, Number(mapCanvas.dataset.matchId), {
        isLive: mapCanvas.dataset.live === 'true',
        battleType: mapCanvas.dataset.battleType,
        mapKind: mapCanvas.dataset.defaultMap,
        pollInterval: 500,
        onRender(view) {
            if (!timeline) return;
            const max = view.getTimelineMax();
            timeline.value = view.timelinePosition * 100;
            currentTime.textContent = view.formatTime(max * view.timelinePosition);
            maxTime.textContent = view.formatTime(max);
        },
        onEvents(events) {
            const feed = document.getElementById('event-feed');
            const items = events.map(event => {
                const item = document.createElement('li');
                const time = document.createElement('time');
                time.textContent = viewer.formatTime(event.timestamp);
                item.append(time, event.msg);
                return item;
            });
            if (items.length === 0) {
                const empty = document.createElement('li');
                empty.className = 'feed-empty';
                empty.textContent = t('viewer.feed_empty');
                items.push(empty);
            }
            feed.replaceChildren(...items);
        },
        onPlayStateChange(isPlaying) {
            playButton.textContent = isPlaying ? t('viewer.pause') : t('viewer.play');
        }
    });

    const mapKindButtons = document.querySelectorAll('[data-map-kind]');
    const markMapKind = () => {
        for (const button of mapKindButtons) button.classList.toggle('active', button.dataset.mapKind === viewer.mapKind);
    };
    for (const button of mapKindButtons) {
        button.addEventListener('click', () => {
            viewer.setMapKind(button.dataset.mapKind);
            markMapKind();
        });
    }
    markMapKind();

    document.getElementById('zoom-in').addEventListener('click', () => viewer.zoomIn());
    document.getElementById('zoom-out').addEventListener('click', () => viewer.zoomOut());
    document.getElementById('zoom-reset').addEventListener('click', () => viewer.resetView());
    // 控件按已保存的设置回填。
    for (const checkbox of document.querySelectorAll('[data-filter]')) {
        checkbox.checked = viewer.filters[checkbox.dataset.filter];
        checkbox.addEventListener('change', () => viewer.setFilter(checkbox.dataset.filter, checkbox.checked));
    }
    const bindSlider = (id, value, setter, format = text => text) => {
        const slider = document.getElementById(id);
        const label = document.getElementById(`${id}-value`);
        slider.value = value;
        label.textContent = format(slider.value);
        slider.addEventListener('input', () => {
            setter(Number(slider.value));
            label.textContent = format(slider.value);
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

    if (playButton) bindSlider('speed-slider', viewer.speed, value => viewer.setSpeed(value), n => t('viewer.speed_value', { n }));

    playButton?.addEventListener('click', () => {
        if (viewer.isPlaying) viewer.pause();
        else viewer.play();
    });
    timeline?.addEventListener('input', () => {
        viewer.pause();
        viewer.setTimeline(Number(timeline.value) / 100);
    });
}
