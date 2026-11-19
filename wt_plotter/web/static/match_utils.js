// 与具体 DOM 无关的战报分类、出击提取与名称格式化工具。

const ZERO_WIDTH = /[\u200b-\u200d\ufeff]/g;

const EVENT_PATTERNS = Object.freeze({
    nuke: /核武器|☢|nuclear|\bnuke\b/i,
    leave: /已离开战局|已掉线|left the match|disconnected/i,
    kill: /击毁|击落|击沉|摧毁|引燃|重创|致命攻击|致命一击|着火|坠毁|自毁|destroyed|shot down|set afire|critical hit|severely damaged|wrecked|crashed|killed/i,
    award: /获得嘉奖|先拔头筹|最后一击|占领|夺取|captured|neutralized|award|first strike|final blow/i,
});

const EVENT_PRIORITY = Object.freeze({ leave: 0, other: 1, award: 2, kill: 3, nuke: 4 });

function formatVehicleName(raw) {
    return raw.split('/').at(-1).replace(/_/g, ' ');
}

function classifyEvent(msg) {
    const clean = msg.replace(ZERO_WIDTH, '');
    if (EVENT_PATTERNS.nuke.test(clean)) return 'nuke';
    if (EVENT_PATTERNS.leave.test(clean)) return 'leave';
    if (EVENT_PATTERNS.kill.test(clean)) return 'kill';
    if (EVENT_PATTERNS.award.test(clean)) return 'award';
    return 'other';
}

function eventPriority(kind) {
    return EVENT_PRIORITY[kind];
}

function matchesFeedFilter(kind, filter) {
    if (filter === 'all') return true;
    if (filter === 'no_leave') return kind !== 'leave';
    if (filter === 'kill') return kind === 'kill' || kind === 'nuke';
    if (filter === 'award') return kind === 'award' || kind === 'nuke';
    return kind === filter;
}

// 从按时间升序的 tick 列表提取实际出场的载具切换节点（仅统计 Player 已在场上的 tick，跳过选车界面点击）。
function extractSorties(ticks, placeholders, playerTickIds) {
    const ignored = new Set(placeholders);
    const sorties = [];
    let current = '';
    for (const tick of ticks) {
        if (!playerTickIds.has(tick.id)) continue;
        const raw = tick.vehicle_type;
        if (!raw || ignored.has(raw) || raw === current) continue;
        current = raw;
        sorties.push({ timestamp: tick.timestamp, vehicle: formatVehicleName(raw), army: tick.army_type });
    }
    return sorties;
}

window.MatchUtils = { formatVehicleName, classifyEvent, eventPriority, matchesFeedFilter, extractSorties };
