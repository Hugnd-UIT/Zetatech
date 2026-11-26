(function() {
    function normInput(prompt = '', input = '') {
        return cleanInput(prompt || input);
    }

    function cleanInput(text) {
        return String(text || '').trim();
    }

    function normMsgs(data = {}) {
        return Array.isArray(data.messages) ? data.messages : [];
    }

    function toolEvents(msgs = []) {
        return msgs.flatMap((msg) => {
            const events = [];
            const calls = Array.isArray(msg.tool_calls) ? msg.tool_calls : [];
            const results = Array.isArray(msg.tool_results) ? msg.tool_results : [];
            calls.forEach((item) => events.push({ type: 'tool_call', data: item }));
            results.forEach((item) => events.push({ type: 'tool_result', data: item }));
            return events;
        });
    }

    function shortPath(val = '', opts = {}) {
        const raw = String(val || '').trim();
        if (!raw) return '';
        const root = String(opts.workspaceRoot || '').trim().replace(/\\/g, '/');
        const norm = raw.replace(/\\/g, '/');
        let out = norm;

        if (root && norm.startsWith(root)) {
            out = norm.slice(root.length).replace(/^\/+/, '');
        }

        out = out
            .replace(/^\/app\/(Plugins|Themes)\/[^/]+\/source\/?/i, '')
            .replace(/^\/Users\/[^/]+\/Desktop\/Zetatech\/(Plugins|Themes)\/[^/]+\/source\/?/i, '')
            .replace(/^\.\//, '');

        if (!out) return '.';
        const parts = out.split('/').filter(Boolean);
        if (parts.length <= 4) return out;
        return `…/${parts.slice(-4).join('/')}`;
    }

    function cutText(val = '', maxLen = 110) {
        const text = String(val || '').replace(/\s+/g, ' ').trim();
        if (!text) return '';
        if (text.length <= maxLen) return text;
        return `${text.slice(0, Math.max(0, maxLen - 1)).trimEnd()}…`;
    }

    function shortPat(val = '') {
        return cutText(String(val || '').trim(), 44);
    }

    function groupItems(entries = []) {
        const list = [];
        (Array.isArray(entries) ? entries : []).forEach((entry) => {
            if (!entry) return;
            const prev = list[list.length - 1];
            const same = prev
                && prev.type === entry.type
                && prev.label === entry.label
                && prev.category === entry.category
                && prev.detail === entry.detail
                && prev.state === entry.state;

            if (same) {
                prev.count = (prev.count || 1) + 1;
                prev.id = `${prev.id}-${prev.count}`;
                return;
            }

            list.push({ ...entry, count: entry.count || 1 });
        });
        return list;
    }

    function buildActivity(events = [], opts = {}) {
        const cfg = opts && typeof opts === 'object' ? opts : {};
        const root = String(cfg.workspaceRoot || '').trim();
        const items = (Array.isArray(events) ? events : []).map((evt, idx) => {
            const type = String(evt?.type || 'event');
            const data = evt?.data && typeof evt.data === 'object' ? evt.data : {};
            const tool = String(data.name || data.toolName || data.tool || '').trim();
            const input = data.input && typeof data.input === 'object' ? data.input : data;
            let label = 'Activity';
            let detail = '';
            let icon = '•';
            let tone = 'neutral';
            let cat = 'activity';
            let state = 'done';
            let hide = false;

            if (type === 'tool_call') {
                cat = 'tool';
                tone = 'running';
                state = 'active';
                if (tool === 'read' || tool === 'file_read') {
                    label = 'File read';
                    detail = shortPath(String(input.path || data.path || '(no path)'), { workspaceRoot: root });
                    icon = '📄';
                } else if (tool === 'grep') {
                    label = 'Code search';
                    const pat = shortPat(input.pattern || '');
                    const path = shortPath(String(input.path || ''), { workspaceRoot: root });
                    detail = [pat ? `pattern: ${pat}` : '', path ? `path: ${path}` : ''].filter(Boolean).join(' • ');
                    icon = '⌕';
                } else if (tool === 'bash') {
                    label = 'Bash';
                    detail = cutText(String(input.command || data.command || '(no command)'), 96);
                    icon = '⌘';
                } else if (tool === 'edit' || tool === 'file_edit') {
                    label = 'File edited';
                    detail = shortPath(String(input.path || data.path || '(no path)'), { workspaceRoot: root });
                    icon = '✎';
                } else if (tool === 'write' || tool === 'file_write') {
                    label = 'File written';
                    detail = shortPath(String(input.path || data.path || '(no path)'), { workspaceRoot: root });
                    icon = '✚';
                } else if (tool === 'run_semgrep') {
                    label = 'Semgrep';
                    detail = cutText(String(input.config || data.config || 'auto'), 72);
                    icon = 'S';
                } else {
                    label = 'Tool';
                    detail = cutText([tool || 'tool', shortPath(String(input.path || input.command || data.path || data.command || '').trim(), { workspaceRoot: root })].filter(Boolean).join(' • '), 96);
                    icon = '⋯';
                }
            } else {
                hide = true;
            }

            return {
                id: `${type}-${idx}`,
                type,
                label,
                detail,
                icon,
                tone,
                category: cat,
                state,
                hidden: hide,
                toolName: tool,
                toolTone: toolTone(tool),
                bashCommand: tool === 'bash' ? String(input.command || data.command || '').trim() : '',
            };
        }).filter((entry) => !entry.hidden);

        const grouped = groupItems(items);
        const last = [...grouped].map((entry, idx) => ({ entry, idx })).reverse().find((item) => item.entry.state === 'active')?.idx;
        return grouped.map((entry, idx) => ({
            ...entry,
            isCurrent: last === idx,
        }));
    }

    function describeEvt(evt = {}) {
        const entry = buildActivity([evt])[0];
        return entry ? `${entry.label}${entry.detail ? `: ${entry.detail}` : ''}` : 'Activity';
    }

    function fmtActivity(evt = {}) {
        const type = String(evt?.type || '');
        const data = evt?.data && typeof evt.data === 'object' ? evt.data : evt;

        if (type === 'agent_started') {
            return `Agent started: ${String(data?.name || 'unknown')}`;
        }
        if (type === 'agent_completed') {
            return `Agent completed: ${String(data?.name || 'unknown')}`;
        }
        if (type === 'task_started') {
            return `Task started: ${String(data?.title || data?.id || 'task')}`;
        }
        if (type === 'task_completed') {
            return `Task completed: ${String(data?.title || data?.id || 'task')}`;
        }
        if (type === 'task_failed') {
            return `Task failed: ${String(data?.title || data?.id || 'task')}`;
        }
        if (type === 'team_started') {
            return `Team started: ${String(data?.name || 'team')}`;
        }

        return describeEvt(evt);
    }

    function extractMsgs(data = {}) {
        return normMsgs(data);
    }

    function mergeMsgs(cur = [], next = []) {
        const out = [];
        const seen = new Set();
        [...(Array.isArray(cur) ? cur : []), ...(Array.isArray(next) ? next : [])].forEach((msg) => {
            if (!msg || typeof msg !== 'object') return;
            const id = msg.id != null ? `id:${String(msg.id)}` : null;
            const fb = `tmp:${String(msg.role || '')}:${String(msg.created_at || '')}:${String(msg.content || '')}`;
            const key = id || fb;
            if (seen.has(key)) return;
            seen.add(key);
            out.push(msg);
        });
        return out;
    }

    function saveMsgs(msgs = []) {
        const state = window.getPluginAiState();
        state.messages = Array.isArray(msgs) ? msgs : [];
        if (typeof window.syncCurrentPluginAiThreadSnapshot === 'function') {
            window.syncCurrentPluginAiThreadSnapshot({ messages: state.messages });
        }
    }

    function pushMsg(msg = {}) {
        const state = window.getPluginAiState();
        state.messages = mergeMsgs(state.messages || [], [msg]);
        if (typeof window.syncCurrentPluginAiThreadSnapshot === 'function') {
            window.syncCurrentPluginAiThreadSnapshot({ messages: state.messages });
        }
        return state.messages;
    }

    function replaceBot(msg = {}) {
        const state = window.getPluginAiState();
        const msgs = Array.isArray(state.messages) ? [...state.messages] : [];
        const idx = msgs.findIndex((item) => item && item.is_pending_assistant);
        if (idx >= 0) {
            msgs[idx] = msg;
        } else {
            msgs.push(msg);
        }
        state.messages = mergeMsgs([], msgs);
        return state.messages;
    }

    function dropBot() {
        const state = window.getPluginAiState();
        state.messages = (Array.isArray(state.messages) ? state.messages : []).filter((item) => !item?.is_pending_assistant);
        if (typeof window.syncCurrentPluginAiThreadSnapshot === 'function') {
            window.syncCurrentPluginAiThreadSnapshot({ messages: state.messages });
        }
        return state.messages;
    }

    function saveAudit(msgs = []) {
        const state = window.getPluginAiState();
        state.events = toolEvents(msgs);
    }

    function addActivity(events = []) {
        const state = window.getPluginAiState();
        const next = Array.isArray(events) ? events.filter(Boolean) : [];
        state.liveActivity = [...(Array.isArray(state.liveActivity) ? state.liveActivity : []), ...next].slice(-100);
        if (typeof window.rememberPluginAiEventsSnapshot === 'function') {
            window.rememberPluginAiEventsSnapshot({
                plugin: state.plugin,
                threadId: state.threadId,
                isTheme: !!state.isTheme,
                events: state.liveActivity,
                createdAt: new Date().toISOString(),
            });
        }
        if (typeof window.syncCurrentPluginAiThreadSnapshot === 'function') {
            window.syncCurrentPluginAiThreadSnapshot({ liveActivity: state.liveActivity, events: state.events });
        }
        return state.liveActivity;
    }

    function applyChunk(chunk = {}) {
        const state = window.getPluginAiState();
        const type = String(chunk?.type || '').trim();
        const data = chunk?.data;

        if (type === 'runtime_event' && data) {
            addActivity([data]);
        } else if (type === 'bridge_event' && data) {
            addActivity([data]);
        } else if (type === 'pending_approval' && data && typeof data === 'object') {
            state.pendingApproval = data;
            if (typeof window.syncCurrentPluginAiThreadSnapshot === 'function') {
                window.syncCurrentPluginAiThreadSnapshot({ pendingApproval: state.pendingApproval, sending: true });
            }
        } else if (type === 'user_message' && data) {
            const cur = Array.isArray(state.messages) ? state.messages : [];
            const stable = cur.filter((item) => !String(item?.id || '').startsWith('tmp-user-') && !item?.is_pending_assistant);
            const pending = cur.filter((item) => item?.is_pending_assistant);
            state.messages = mergeMsgs(stable, [data, ...pending]);
        } else if (type === 'final' && data && typeof data === 'object') {
            const msgs = [];
            if (data.user_message) msgs.push(data.user_message);
            if (data.assistant_message) msgs.push(data.assistant_message);
            const done = (state.messages || []).filter((item) => !item?.is_pending_assistant);
            state.messages = mergeMsgs(done, msgs);
            state.events = Array.isArray(data.team_events) ? data.team_events : [];
            state.liveActivity = state.events.length ? state.events : (state.liveActivity || []);
            state.pendingApproval = data.pending_approval && typeof data.pending_approval === 'object'
                ? data.pending_approval
                : null;
            if (typeof window.rememberPluginAiEventsSnapshot === 'function') {
                window.rememberPluginAiEventsSnapshot({
                    plugin: state.plugin,
                    threadId: state.threadId,
                    isTheme: !!state.isTheme,
                    events: state.liveActivity,
                    createdAt: new Date().toISOString(),
                });
            }
            if (typeof window.syncCurrentPluginAiThreadSnapshot === 'function') {
                window.syncCurrentPluginAiThreadSnapshot({
                    messages: state.messages,
                    events: state.events,
                    liveActivity: state.liveActivity,
                    sending: false,
                });
            }
            if (data.thread && typeof window.replacePluginAiThreadInState === 'function') {
                window.replacePluginAiThreadInState(data.thread);
                if (typeof window.rememberPluginAiThread === 'function') {
                    window.rememberPluginAiThread(data.thread);
                }
            }
        }
        return state;
    }

    function chatLabel(thread = {}, idx = 0) {
        const title = String(thread.title || '').trim();
        const slug = String(thread.plugin_slug || '').trim();
        if (title) {
            if (slug && title === slug) {
                return 'Chat 1';
            }
            if (slug) {
                const esc = slug.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                const match = title.match(new RegExp(`^${esc} Chat (\\d+)$`, 'i'));
                if (match) {
                    return `Chat ${match[1]}`;
                }
            }
            return title;
        }
        const pos = Number(idx || 0) + 1;
        return `Chat ${pos}`;
    }

    function chatMeta(thread = {}) {
        const updated = String(thread.updated_at || thread.created_at || '').trim();
        return updated || 'No activity yet';
    }

    function activeThread() {
        const state = window.getPluginAiState();
        return Array.isArray(state.threads)
            ? state.threads.find((item) => Number(item?.id || 0) === Number(state.threadId || 0)) || null
            : null;
    }

    function srcStatus() {
        const state = window.getPluginAiState();
        const thread = activeThread();
        const fb = state.sourceStatus && typeof state.sourceStatus === 'object' ? state.sourceStatus : {};
        const avail = !!(thread?.source_available ?? fb.source_available);
        const mode = String(thread?.source_context_mode || fb.source_context_mode || 'metadata_only');
        const path = String(thread?.source_path || fb.source_path || '');
        const work = String(thread?.workspace_path || fb.workspace_path || path || '');
        return {
            source_available: avail,
            source_context_mode: mode,
            source_path: path,
            workspace_path: work,
        };
    }

    function renderSrcCard() {
        const state = window.getPluginAiState();
        const src = srcStatus();
        const card = document.getElementById('plugin-ai-source-card');
        const avail = document.getElementById('plugin-ai-source-availability');
        const ctx = document.getElementById('plugin-ai-source-context');
        const path = document.getElementById('plugin-ai-source-path');
        const btn = document.getElementById('plugin-ai-source-download-btn');
        if (!card || !avail || !ctx || !path || !btn) return;

        const hasBot = Array.isArray(state.messages)
            && state.messages.some((item) => String(item?.role || '') === 'assistant' && !item?.is_pending_assistant);
        card.classList.toggle('is-hidden', hasBot && !state.sourcePreparing);

        avail.textContent = src.source_available ? 'Ready' : 'Not downloaded';
        ctx.textContent = src.source_context_mode === 'attached'
            ? 'Attached'
            : (src.source_context_mode === 'available' ? 'Available' : 'Metadata-only');
        path.textContent = shortPath(src.source_path || '', { workspaceRoot: src.workspace_path || '' }) || '—';
        btn.textContent = state.sourcePreparing
            ? 'Preparing...'
            : (src.source_available ? 'Re-download' : 'Download');
        btn.disabled = !!state.sourcePreparing;
    }

    function inlineMd(text = '') {
        const tokens = [];
        let html = escapeHtml(String(text || ''));

        html = html.replace(/`([^`]+)`/g, (_, code) => {
            const tok = `@@INLINE_CODE_${tokens.length}@@`;
            tokens.push(`<code>${escapeHtml(code)}</code>`);
            return tok;
        });

        html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer noopener">$1</a>');
        html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
        html = html.replace(/__([^_]+)__/g, '<strong>$1</strong>');
        html = html.replace(/~~([^~]+)~~/g, '<del>$1</del>');
        html = html.replace(/(^|\W)\*([^*]+)\*(?=\W|$)/g, '$1<em>$2</em>');
        html = html.replace(/(^|\W)_([^_]+)_(?=\W|$)/g, '$1<em>$2</em>');

        tokens.forEach((val, idx) => {
            html = html.replace(`@@INLINE_CODE_${idx}@@`, val);
        });
        return html;
    }

    function tableRow(line = '') {
        const raw = String(line || '').trim().replace(/^\|/, '').replace(/\|$/, '');
        return raw.split('|').map((cell) => inlineMd(cell.trim()));
    }

    function isTableSep(line = '') {
        const raw = String(line || '').trim();
        return /^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$/.test(raw);
    }

    function normPara(lines = []) {
        const parts = [];
        (Array.isArray(lines) ? lines : []).forEach((line) => {
            const val = String(line || '').trim();
            if (!val) return;
            if (!parts.length) {
                parts.push(val);
                return;
            }
            if (/^[,.;:!?%)\]\}]+$/.test(val)) {
                parts[parts.length - 1] += val;
                return;
            }
            if (/^[,.;:!?%)\]\}]/.test(val)) {
                parts[parts.length - 1] += val;
                return;
            }
            if (/^["'”’]/.test(val)) {
                parts[parts.length - 1] += ` ${val}`;
                return;
            }
            parts.push(val);
        });

        return parts.reduce((out, part) => {
            if (!out) return part;
            if (/[\s([{-]$/.test(out)) return `${out}${part}`;
            if (/^[,.;:!?%)\]\}]/.test(part)) return `${out}${part}`;
            return `${out} ${part}`;
        }, '');
    }

    function paraHtml(lines = []) {
        const text = normPara(lines);
        return text ? `<p>${inlineMd(text)}</p>` : '';
    }

    function mergeBreak(_lines = [], _next = '') {
        return false;
    }

    function listHtml(lines = [], type = 'ul') {
        const tag = type === 'ol' ? 'ol' : 'ul';
        const items = lines
            .map((line) => String(line || '').trim())
            .map((line) => line.replace(type === 'ol' ? /^\d+\.\s+/ : /^[-*+]\s+/, ''))
            .map((line) => `<li>${inlineMd(normPara([line]))}</li>`)
            .join('');
        return items ? `<${tag}>${items}</${tag}>` : '';
    }

    function quoteHtml(lines = []) {
        const body = paraHtml(lines.map((line) => String(line || '').replace(/^>\s?/, '')));
        return body ? `<blockquote>${body}</blockquote>` : '';
    }

    function tableHtml(lines = []) {
        if (lines.length < 2) return paraHtml(lines);
        const head = tableRow(lines[0]);
        const rows = lines.slice(2).map((line) => tableRow(line));
        return `
            <div class="plugin-ai-table-wrap">
                <table>
                    <thead><tr>${head.map((cell) => `<th>${cell}</th>`).join('')}</tr></thead>
                    <tbody>${rows.map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join('')}</tr>`).join('')}</tbody>
                </table>
            </div>
        `;
    }

    function fieldKey(val = '') {
        return String(val || '').trim().toLowerCase().replace(/\s+/g, '_');
    }

    function sevTone(val = '') {
        const sev = String(val || '').trim().toLowerCase();
        if (sev === 'critical') return 'critical';
        if (sev === 'high') return 'high';
        if (sev === 'medium') return 'medium';
        if (sev === 'low') return 'low';
        return 'info';
    }

    function escAttr(val = '') {
        return escapeHtml(String(val || '').trim().toLowerCase());
    }

    function parseFindings(src = '') {
        const raw = String(src || '').replace(/\r\n/g, '\n');
        if (!raw.trim()) return [];

        const lines = raw.split('\n');
        const list = [];
        let cur = null;
        let field = '';

        const pushCur = () => {
            if (!cur || !String(cur.title || '').trim()) return;
            list.push({ ...cur });
            cur = null;
            field = '';
        };

        lines.forEach((rawLine) => {
            const line = String(rawLine || '');
            const trimmed = line.trim();

            const match = trimmed.match(/^##\s+Finding:\s*(.+)$/i);
            if (match) {
                pushCur();
                cur = {
                    title: match[1].trim(),
                    severity: '',
                    confidence: '',
                    impact: '',
                    exploitability: '',
                    evidence: [],
                    affected_files: [],
                    recommended_fix: [],
                    notes: [],
                };
                field = '';
                return;
            }

            if (!cur || !trimmed) return;

            const fMatch = trimmed.match(/^[-*]\s+([^:]+):\s*(.*)$/);
            if (fMatch) {
                const key = fieldKey(fMatch[1]);
                const val = String(fMatch[2] || '').trim();
                field = '';

                if (key === 'severity' || key === 'confidence' || key === 'impact' || key === 'exploitability') {
                    cur[key] = val;
                    return;
                }

                if (key === 'evidence' || key === 'affected_files' || key === 'recommended_fix' || key === 'notes') {
                    field = key;
                    if (val) cur[key].push(val);
                    return;
                }
            }

            const bullet = trimmed.match(/^[-*]\s+(.+)$/);
            if (bullet && field && Array.isArray(cur[field])) {
                cur[field].push(bullet[1].trim());
                return;
            }

            if (field && Array.isArray(cur[field])) {
                cur[field].push(trimmed);
                return;
            }

            cur.notes.push(trimmed);
        });

        pushCur();
        return list.filter((item) => String(item.title || '').trim());
    }

    function renderFindings(src = '') {
        const list = parseFindings(src);
        if (!list.length) return '';

        const cards = list.map((item) => {
            const sev = String(item.severity || 'Info').trim() || 'Info';
            const conf = String(item.confidence || 'Unknown').trim() || 'Unknown';
            const imp = String(item.impact || '').trim();
            const exp = String(item.exploitability || '').trim();
            const ev = Array.isArray(item.evidence) ? item.evidence.filter(Boolean) : [];
            const files = Array.isArray(item.affected_files) ? item.affected_files.filter(Boolean) : [];
            const fixes = Array.isArray(item.recommended_fix) ? item.recommended_fix.filter(Boolean) : [];
            const notes = Array.isArray(item.notes) ? item.notes.filter(Boolean) : [];
            const tone = sevTone(sev);

            return `
                <article class="plugin-ai-finding-card" data-severity="${escAttr(tone)}">
                    <div class="plugin-ai-finding-card-head">
                        <div>
                            <div class="plugin-ai-finding-kicker">Security finding</div>
                            <h3>${inlineMd(item.title)}</h3>
                        </div>
                        <div class="plugin-ai-finding-badges">
                            <span class="plugin-ai-finding-badge severity-${escAttr(tone)}">${escapeHtml(sev)}</span>
                            <span class="plugin-ai-finding-badge confidence">${escapeHtml(conf)} confidence</span>
                        </div>
                    </div>
                    <div class="plugin-ai-finding-grid">
                        ${imp ? `<section><strong>Impact</strong><p>${inlineMd(imp)}</p></section>` : ''}
                        ${exp ? `<section><strong>Exploitability</strong><p>${inlineMd(exp)}</p></section>` : ''}
                        ${ev.length ? `<section><strong>Evidence</strong><ul>${ev.map((row) => `<li>${inlineMd(row)}</li>`).join('')}</ul></section>` : ''}
                        ${files.length ? `<section><strong>Affected files</strong><ul>${files.map((row) => `<li><code>${escapeHtml(row)}</code></li>`).join('')}</ul></section>` : ''}
                        ${fixes.length ? `<section><strong>Recommended fix</strong><ul>${fixes.map((row) => `<li>${inlineMd(row)}</li>`).join('')}</ul></section>` : ''}
                        ${notes.length ? `<section><strong>Notes</strong><ul>${notes.map((row) => `<li>${inlineMd(row)}</li>`).join('')}</ul></section>` : ''}
                    </div>
                </article>
            `;
        }).join('');

        return `<div class="plugin-ai-findings">${cards}</div>`;
    }

    function renderMd(src = '') {
        const raw = String(src || '').replace(/\r\n/g, '\n');
        if (!raw.trim()) return '';

        const cards = renderFindings(raw);
        const blocks = [];
        const body = raw.replace(/```([\w-]*)\n([\s\S]*?)```/g, (_, lang, code) => {
            const idx = blocks.length;
            blocks.push({ lang: String(lang || '').trim(), code: String(code || '').replace(/\n$/, '') });
            return `\n@@CODEBLOCK_${idx}@@\n`;
        });

        const lines = body.split('\n');
        const html = [];
        let idx = 0;

        while (idx < lines.length) {
            const line = String(lines[idx] || '');
            const trimmed = line.trim();

            if (!trimmed) {
                idx += 1;
                continue;
            }

            const cMatch = trimmed.match(/^@@CODEBLOCK_(\d+)@@$/);
            if (cMatch) {
                const block = blocks[Number(cMatch[1])] || { lang: '', code: '' };
                const attr = block.lang ? ` data-language="${escapeHtml(block.lang)}"` : '';
                const badge = block.lang ? `<span class="plugin-ai-code-lang">${escapeHtml(block.lang)}</span>` : '';
                html.push(`<pre class="plugin-ai-code-block"${attr}>${badge}<code>${escapeHtml(block.code)}</code></pre>`);
                idx += 1;
                continue;
            }

            if (/^(-{3,}|\*{3,}|_{3,})$/.test(trimmed)) {
                html.push('<hr>');
                idx += 1;
                continue;
            }

            const hMatch = trimmed.match(/^(#{1,6})\s+(.*)$/);
            if (hMatch) {
                const lvl = Math.min(6, hMatch[1].length);
                html.push(`<h${lvl}>${inlineMd(hMatch[2].trim())}</h${lvl}>`);
                idx += 1;
                continue;
            }

            if (trimmed.startsWith('>')) {
                const qLines = [];
                while (idx < lines.length && String(lines[idx] || '').trim().startsWith('>')) {
                    qLines.push(String(lines[idx] || '').trim());
                    idx += 1;
                }
                html.push(quoteHtml(qLines));
                continue;
            }

            if (trimmed.includes('|') && idx + 1 < lines.length && isTableSep(lines[idx + 1])) {
                const tLines = [trimmed, String(lines[idx + 1] || '').trim()];
                idx += 2;
                while (idx < lines.length) {
                    const row = String(lines[idx] || '').trim();
                    if (!row || !row.includes('|')) break;
                    tLines.push(row);
                    idx += 1;
                }
                html.push(tableHtml(tLines));
                continue;
            }

            if (/^\d+\.\s+/.test(trimmed)) {
                const lLines = [];
                while (idx < lines.length && /^\d+\.\s+/.test(String(lines[idx] || '').trim())) {
                    lLines.push(String(lines[idx] || '').trim());
                    idx += 1;
                }
                html.push(listHtml(lLines, 'ol'));
                continue;
            }

            if (/^[-*+]\s+/.test(trimmed)) {
                const lLines = [];
                while (idx < lines.length && /^[-*+]\s+/.test(String(lines[idx] || '').trim())) {
                    lLines.push(String(lines[idx] || '').trim());
                    idx += 1;
                }
                html.push(listHtml(lLines, 'ul'));
                continue;
            }

            const pLines = [];
            while (idx < lines.length) {
                const cur = String(lines[idx] || '');
                const curTrim = cur.trim();

                if (!curTrim) {
                    let nextIdx = idx + 1;
                    while (nextIdx < lines.length && !String(lines[nextIdx] || '').trim()) {
                        nextIdx += 1;
                    }
                    const nextTrim = nextIdx < lines.length ? String(lines[nextIdx] || '').trim() : '';
                    if (mergeBreak(pLines, nextTrim)) {
                        idx = nextIdx;
                        continue;
                    }
                    break;
                }

                if (/^@@CODEBLOCK_\d+@@$/.test(curTrim)) break;
                if (/^(#{1,6})\s+/.test(curTrim)) break;
                if (/^(-{3,}|\*{3,}|_{3,})$/.test(curTrim)) break;
                if (curTrim.startsWith('>')) break;
                if (/^\d+\.\s+/.test(curTrim)) break;
                if (/^[-*+]\s+/.test(curTrim)) break;
                if (curTrim.includes('|') && idx + 1 < lines.length && isTableSep(lines[idx + 1])) break;
                pLines.push(curTrim);
                idx += 1;
            }
            html.push(paraHtml(pLines));
        }

        const mdHtml = html.filter(Boolean).join('');
        return `${cards || ''}${mdHtml}`;
    }

    function renderChats(threads = [], activeId = null) {
        const box = document.getElementById('plugin-ai-sessions');
        if (!box) return;

        if (!Array.isArray(threads) || threads.length === 0) {
            box.innerHTML = '<div class="plugin-ai-session-empty">No chats yet.</div>';
            return;
        }

        box.innerHTML = threads
            .map((thread, idx) => {
                const id = Number(thread.id || 0);
                const cls = id === Number(activeId || 0) ? ' is-active' : '';
                const state = typeof window.getPluginAiState === 'function' ? window.getPluginAiState() : {};
                const snap = typeof window.getPluginAiThreadUiSnapshot === 'function'
                    ? window.getPluginAiThreadUiSnapshot(String(thread.plugin_slug || state.plugin || '').trim(), id, !!thread.is_theme)
                    : null;
                const running = !!snap?.sending;
                const dur = running && typeof window.formatPluginAiRunDuration === 'function'
                    ? window.formatPluginAiRunDuration(snap?.runStartedAt)
                    : '';
                const meta = running
                    ? `<span class="plugin-ai-session-running"><span class="plugin-ai-session-running-dot"></span>Running${dur ? ` • ${escapeHtml(dur)}` : ''}</span>`
                    : '';
                return `
                    <div class="plugin-ai-session-item${cls}${running ? ' is-running' : ''}" data-thread-id="${id}">
                        <button type="button" class="plugin-ai-session-main" data-thread-id="${id}">
                            <strong>${escapeHtml(chatLabel(thread, idx))}</strong>
                            <span>${escapeHtml(chatMeta(thread))}</span>
                            ${meta}
                        </button>
                        <div class="plugin-ai-session-actions">
                            <button type="button" class="plugin-ai-session-icon" data-thread-rename="${id}" title="Rename chat" aria-label="Rename chat">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"></path><path d="M16.5 3.5a2.121 2.121 0 1 1 3 3L7 19l-4 1 1-4 12.5-12.5z"></path></svg>
                            </button>
                            <button type="button" class="plugin-ai-session-icon is-danger" data-thread-delete="${id}" title="Delete chat" aria-label="Delete chat">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"></path><path d="M10 11v6"></path><path d="M14 11v6"></path><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"></path></svg>
                            </button>
                        </div>
                    </div>
                `;
            })
            .join('');
    }

    function updateChatUi() {
        const state = window.getPluginAiState();
        renderChats(state.threads || [], state.threadId);
    }

    function emptyMsgs() {
        renderMsgs([]);
    }

    function emptyActivity() {
        renderActivity([]);
    }

    function visibleItems(entries = [], expanded = false) {
        const list = Array.isArray(entries) ? entries : [];
        if (expanded) return list;
        return list.slice(-3);
    }

    function escHtmlAttr(val = '') {
        return String(val ?? '')
            .replace(/&/g, '&amp;')
            .replace(/"/g, '&quot;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
    }

    function toolTone(name = '') {
        const tool = String(name || '').trim().toLowerCase();
        if (tool === 'bash') return 'bash';
        if (tool === 'read' || tool === 'file_read') return 'read';
        if (tool === 'grep') return 'grep';
        if (tool === 'write' || tool === 'file_write') return 'write';
        if (tool === 'edit' || tool === 'file_edit') return 'edit';
        return 'neutral';
    }

    function pickTrace(events = []) {
        const list = Array.isArray(events) ? events : [];
        for (let idx = list.length - 1; idx >= 0; idx -= 1) {
            const evt = list[idx];
            const type = String(evt?.type || '');
            const data = evt?.data && typeof evt.data === 'object' ? evt.data : {};
            if (type === 'decision_trace') {
                return data;
            }
            if (type === 'intent_resolved' && data.decision_trace && typeof data.decision_trace === 'object') {
                return data.decision_trace;
            }
        }
        return {};
    }

    function traceInfo(events = []) {
        const trace = pickTrace(events);
        const norm = trace.normalized_decision && typeof trace.normalized_decision === 'object'
            ? trace.normalized_decision
            : trace;
        return {
            trace,
            normalized: norm,
            reason: String(norm.reason || trace.reason || ''),
            strategy: String(norm.strategy || trace.strategy || ''),
            executionMode: String(norm.execution_mode || trace.execution_mode || ''),
            teamMode: String(norm.team_mode || trace.team_mode || ''),
            compositionSource: String(trace.composition_source || norm.composition_source || ''),
            needsTools: norm.needs_tools ?? trace.needs_tools,
            securityFocus: norm.security_focus ?? trace.security_focus,
        };
    }

    function execItems(events = []) {
        const list = Array.isArray(events) ? events : [];
        const state = window.getPluginAiState ? window.getPluginAiState() : {};
        const root = String(state?.liveActivityOptions?.workspaceRoot || '').trim();
        const items = [];

        list.forEach((evt) => {
            const type = String(evt?.type || '').trim();
            if (type !== 'tool_call') return;

            const data = evt?.data && typeof evt.data === 'object' ? evt.data : {};
            const tool = String(data.name || data.toolName || data.tool || '').trim();
            const input = data.input && typeof data.input === 'object' ? data.input : data;

            if (tool === 'bash') {
                const rawCmd = String(input.command || data.command || '').trim();
                const cmd = cutText(rawCmd, 140);
                items.push({
                    label: 'Tool call • bash',
                    value: cmd || '(no command)',
                    copyText: rawCmd || undefined,
                });
                return;
            }

            if (tool === 'read' || tool === 'file_read') {
                const path = shortPath(String(input.path || data.path || '').trim(), { workspaceRoot: root });
                items.push({ label: `Tool call • ${tool || 'read'}`, value: path || '(no path)' });
                return;
            }

            if (tool === 'grep') {
                const pat = shortPat(String(input.pattern || '').trim());
                const path = shortPath(String(input.path || data.path || '').trim(), { workspaceRoot: root }) || '.';
                items.push({
                    label: 'Tool call • grep',
                    value: [pat ? `pattern: ${pat}` : '', `path: ${path}`].filter(Boolean).join(' • ') || '(no input)',
                });
                return;
            }

            if (tool === 'write' || tool === 'file_write' || tool === 'edit' || tool === 'file_edit') {
                const path = shortPath(String(input.path || data.path || '').trim(), { workspaceRoot: root });
                items.push({ label: `Tool call • ${tool}`, value: path || '(no path)' });
                return;
            }

            const fb = cutText(JSON.stringify(input), 180);
            items.push({ label: `Tool call${tool ? ` • ${tool}` : ''}`, value: fb || '(no input)' });
        });

        return items;
    }

    function execSummary(events = []) {
        const list = Array.isArray(events) ? events : [];
        const agents = new Set();
        const tools = new Set();
        let bashCount = 0;

        list.forEach((evt) => {
            const type = String(evt?.type || '');
            const data = evt?.data && typeof evt.data === 'object' ? evt.data : {};
            if (type === 'agent_started' || type === 'agent_completed') {
                const name = String(data.name || '').trim();
                if (name) agents.add(name);
            }
            if (type === 'tool_call') {
                const tool = String(data.name || data.toolName || data.tool || '').trim();
                if (tool) tools.add(tool);
                if (tool === 'bash') bashCount += 1;
            }
        });

        const details = execItems(list);
        return {
            totalEvents: details.length,
            agents: [...agents],
            tools: [...tools],
            bashCount,
            details,
        };
    }

    function renderRail(entries = [], opts = {}) {
        const expanded = !!opts.expanded;
        const visible = visibleItems(entries, expanded);
        const toggleLabel = expanded ? 'Show less' : `Show all activity (${entries.length})`;
        const sub = expanded
            ? `${entries.length} events visible`
            : `${Math.min(entries.length, 3)} of ${entries.length} events visible`;

        return `
            <div class="plugin-ai-live-activity" aria-live="polite">
                <div class="plugin-ai-live-activity-head plugin-ai-live-activity-head--space-between">
                    <div class="plugin-ai-live-activity-title-wrap">
                        <span>Working</span>
                        <span class="plugin-ai-live-activity-dots"><i></i><i></i><i></i></span>
                    </div>
                    ${entries.length > 3 ? `<button type="button" class="plugin-ai-inline-toggle" data-plugin-ai-toggle="activityExpanded">${escapeHtml(toggleLabel)}</button>` : ''}
                </div>
                <div class="plugin-ai-live-activity-subhead">${escapeHtml(sub)}</div>
                <div class="plugin-ai-live-activity-rail${expanded ? ' is-expanded' : ''}">
                    ${visible
                        .map((entry, idx) => `
                            <div class="plugin-ai-live-activity-item${entry.isCurrent ? ' is-current' : ''}${idx === visible.length - 1 ? ' is-latest' : ' is-history'}" data-activity-type="${escapeHtml(entry.type)}" data-tone="${escapeHtml(entry.tone || 'neutral')}" data-category="${escapeHtml(entry.category || 'activity')}">
                                <div class="plugin-ai-activity-row-head">
                                    <em class="plugin-ai-activity-icon" aria-hidden="true">${escapeHtml(entry.icon || '•')}</em>
                                    <strong>${escapeHtml(entry.label)}</strong>
                                    ${entry.count > 1 ? `<small>×${escapeHtml(String(entry.count))}</small>` : ''}
                                    ${entry.bashCommand ? `<button type="button" class="plugin-ai-copy-btn plugin-ai-copy-btn--icon" data-copy-label="⧉" data-copy-text="${escHtmlAttr(entry.bashCommand)}" aria-label="Copy command" title="Copy command">⧉</button>` : ''}
                                    ${entry.isCurrent ? '<mark>Now</mark>' : '<mark class="is-history">Past</mark>'}
                                </div>
                                ${entry.detail ? `<span>${escapeHtml(entry.detail)}</span>` : ''}
                            </div>
                        `)
                        .join('')}
                </div>
            </div>
        `;
    }

    function renderTrace(events = []) {
        const info = traceInfo(events);
        const team = String(info.teamMode || '').trim().toLowerCase();
        const line = [
            info.strategy ? `Strategy: ${info.strategy}` : '',
            (info.teamMode && team !== 'single_agent') ? `Team: ${info.teamMode}` : '',
            typeof info.needsTools === 'boolean' ? `Tools: ${info.needsTools ? 'on' : 'off'}` : '',
        ].filter(Boolean).join(' • ');

        if (!line) {
            return '';
        }

        return `
            <section class="plugin-ai-decision-trace">
                <div class="plugin-ai-execution-summary-head">
                    <div>
                        <strong>Run info</strong>
                        <p>${escapeHtml(line)}</p>
                    </div>
                </div>
            </section>
        `;
    }

    function modeLabel(mode = '') {
        const norm = String(mode || '').trim().toLowerCase();
        if (norm === 'manual') return 'Manual approval';
        if (norm === 'auto_approve') return 'Auto approve';
        if (norm === 'off') return 'Approval off (YOLO • Dangerous)';
        return norm || 'Unknown';
    }

    function taskLabel(task = {}, idx = 0) {
        if (!task || typeof task !== 'object') return `Task ${idx + 1}`;
        return String(task.title || task.id || `Task ${idx + 1}`).trim() || `Task ${idx + 1}`;
    }

    function taskMeta(task = {}) {
        if (!task || typeof task !== 'object') return '';
        const status = String(task.status || '').trim();
        const who = String(task.assignee || '').trim();
        const id = String(task.id || '').trim();
        return [
            status ? `status: ${status}` : '',
            who ? `assignee: ${who}` : '',
            id ? `id: ${id}` : '',
        ].filter(Boolean).join(' • ');
    }

    function scopeInfo(events = [], req = {}) {
        const list = Array.isArray(events) ? events : [];
        const calls = [];

        list.forEach((evt) => {
            const type = String(evt?.type || '').trim();
            if (type !== 'tool_call') return;
            const data = evt?.data && typeof evt.data === 'object' ? evt.data : {};
            const input = data.input && typeof data.input === 'object' ? data.input : data;
            const name = String(data.name || data.toolName || data.tool || '').trim();
            if (!name) return;
            calls.push({ name, input });
        });

        const tools = [...new Set(calls.map((call) => call.name))];
        const cmds = calls
            .filter((call) => call.name === 'bash')
            .map((call) => String(call.input?.command || '').trim())
            .filter(Boolean);
        const reads = calls
            .filter((call) => call.name === 'read' || call.name === 'file_read')
            .map((call) => String(call.input?.path || '').trim())
            .filter(Boolean);

        const done = Array.isArray(req.completedTasks) ? req.completedTasks : [];
        const next = Array.isArray(req.nextTasks) ? req.nextTasks : [];

        return {
            toolCallCount: calls.length,
            uniqueTools: tools,
            bashCommands: cmds,
            readTargets: reads,
            completedTasks: done,
            nextTasks: next,
            scope: String(req.scope || '').trim(),
            toolName: String(req.toolName || '').trim(),
            toolInput: req.toolInput && typeof req.toolInput === 'object' ? req.toolInput : null,
            riskLevel: String(req.riskLevel || '').trim(),
            riskReason: String(req.riskReason || '').trim(),
            summary: String(req.summary || '').trim(),
        };
    }

    function renderStruct(msg = {}) {
        const struct = msg && typeof msg.structured === 'object' ? msg.structured : null;
        if (!struct) return '';
        return `
            <section class="plugin-ai-execution-summary is-expanded">
                <div class="plugin-ai-execution-summary-head">
                    <div>
                        <strong>Structured output</strong>
                        <p>Validated JSON returned by Open Multi-Agent</p>
                    </div>
                </div>
                <div class="plugin-ai-execution-summary-details">
                    <div class="plugin-ai-execution-detail-row">
                        <strong>JSON</strong>
                        <span>${escapeHtml(JSON.stringify(struct, null, 2))}</span>
                    </div>
                </div>
            </section>
        `;
    }

    function renderApproval(pending = null, events = []) {
        if (!pending || typeof pending !== 'object' || String(pending.status || '') !== 'pending') {
            return '';
        }

        const req = pending.request_payload && typeof pending.request_payload === 'object'
            ? pending.request_payload
            : {};
        const info = scopeInfo(events, req);
        const next = info.nextTasks;
        const done = info.completedTasks;
        const modeTxt = modeLabel(pending.mode || req.mode || 'manual');

        const toolsLine = info.uniqueTools.length ? info.uniqueTools.join(', ') : 'No tool metadata available';
        const lastBash = info.bashCommands.length ? info.bashCommands[info.bashCommands.length - 1] : '';
        const lastRead = info.readTargets.length ? info.readTargets[info.readTargets.length - 1] : '';

        const scope = String(info.scope || '').trim();
        const tool = String(info.toolName || '').trim();
        const risk = String(info.riskLevel || '').trim();
        const reason = String(info.riskReason || '').trim();
        const sumTxt = String(info.summary || '').trim();
        const input = info.toolInput && typeof info.toolInput === 'object' ? info.toolInput : null;
        const cmd = tool === 'bash' ? String(input?.command || '').trim() : '';
        const path = input && typeof input.path === 'string' ? String(input.path).trim() : '';

        const rows = next.length
            ? next
                .slice(0, 4)
                .map((task, idx) => {
                    const label = taskLabel(task, idx);
                    const meta = taskMeta(task);
                    return `<li><strong>${escapeHtml(label)}</strong>${meta ? `<span>${escapeHtml(meta)}</span>` : ''}</li>`;
                })
                .join('')
            : '<li><strong>No next task details supplied.</strong><span>The runtime requested approval without detailed task metadata.</span></li>';

        const isTool = scope === 'tool_call';
        const head = isTool ? 'Tool approval required' : 'Manual approval required';
        const sub = isTool
            ? 'Review the requested command before continuing.'
            : 'This run is paused before continuing the pipeline.';

        const toneCls = tool ? `tone-${String(tool).toLowerCase().replace(/[^a-z0-9_-]+/g, '-')}` : '';
        const actionTxt = (() => {
            if (tool === 'write' && path) return `write ${shortPath(path)}`;
            if (tool === 'edit' && path) return `edit ${shortPath(path)}`;
            if (tool === 'read' && path) return `read ${shortPath(path)}`;
            if (tool === 'bash' && cmd) return cmd;
            if (path) return `${tool || 'tool'} ${shortPath(path)}`;
            if (sumTxt) return sumTxt;
            return tool || 'Tool call';
        })();
        const toolCard = isTool
            ? `
                <div class="plugin-ai-approval-card">
                    <div class="plugin-ai-approval-card__top">
                        <div>
                            <div class="plugin-ai-approval-card__eyebrow">Pending action</div>
                            <div class="plugin-ai-approval-card__title">${escapeHtml(sumTxt || 'A tool call needs your approval.')}</div>
                        </div>
                        <span class="plugin-ai-tool-badge ${escapeHtml(toneCls)}">${escapeHtml(tool || 'tool')}</span>
                    </div>
                    <div class="plugin-ai-approval-command">${escapeHtml(actionTxt)}</div>
                    ${path && tool !== 'bash' ? `<div class="plugin-ai-approval-meta"><span>Target</span><code>${escapeHtml(shortPath(path))}</code></div>` : ''}
                    ${risk ? `<div class="plugin-ai-approval-meta"><span>Risk</span><strong>${escapeHtml(risk)}${reason ? ` • ${escapeHtml(reason)}` : ''}</strong></div>` : ''}
                </div>
              `
            : '';

        const mainRows = isTool
            ? toolCard
            : `
                    <div class="plugin-ai-execution-detail-row"><strong>Approve will</strong><span>Continue pending tasks with the same tools for this run.</span></div>
                    <div class="plugin-ai-execution-detail-row"><strong>Reject will</strong><span>Stop the run and mark it as failed.</span></div>
                    <div class="plugin-ai-execution-detail-row"><strong>Tools used so far</strong><span>${escapeHtml(toolsLine)}</span></div>
                    ${lastBash ? `<div class="plugin-ai-execution-detail-row has-copy"><strong>Latest bash command</strong><span>${escapeHtml(cutText(lastBash, 220))}</span><button type="button" class="plugin-ai-copy-btn plugin-ai-copy-btn--inline" data-copy-text="${escHtmlAttr(lastBash)}">Copy</button></div>` : ''}
                    ${lastRead ? `<div class="plugin-ai-execution-detail-row"><strong>Latest read target</strong><span>${escapeHtml(shortPath(lastRead))}</span></div>` : ''}
                    <div class="plugin-ai-execution-detail-row"><strong>Upcoming tasks</strong><span>Review the next queued tasks below before you approve.</span></div>
              `;

        return `
            <section class="plugin-ai-execution-summary is-expanded${isTool ? ' is-tool-approval' : ''}">
                <div class="plugin-ai-execution-summary-head">
                    <div>
                        <strong>${escapeHtml(head)}</strong>
                        ${sub ? `<p>${escapeHtml(sub)}</p>` : ''}
                    </div>
                </div>
                ${isTool ? '' : `<div class="plugin-ai-summary-chips">
                    <span class="plugin-ai-summary-chip">mode: ${escapeHtml(modeTxt)}</span>
                    <span class="plugin-ai-summary-chip">tool calls: ${escapeHtml(String(info.toolCallCount))}</span>
                    <span class="plugin-ai-summary-chip">completed: ${escapeHtml(String(done.length))}</span>
                    <span class="plugin-ai-summary-chip">next: ${escapeHtml(String(next.length))}</span>
                </div>`}
                <div class="plugin-ai-execution-summary-details${isTool ? ' is-tool-approval' : ''}">
                    ${mainRows}
                </div>
                ${isTool ? '' : `<div class="plugin-ai-approval-task-block">
                    <ul class="plugin-ai-approval-task-list">${rows}</ul>
                </div>`}
                <div class="plugin-ai-approval-actions${isTool ? ' is-tool-approval' : ''}">
                    <button type="button" class="secondary-btn plugin-ai-approval-btn plugin-ai-approval-btn--approve" id="plugin-ai-approve-run">Approve</button>
                    <button type="button" class="danger-btn plugin-ai-approval-btn plugin-ai-approval-btn--reject" id="plugin-ai-reject-run">Reject</button>
                </div>
            </section>
        `;
    }

    function renderSummary(events = [], opts = {}) {
        const expanded = !!opts.expanded;
        const sum = execSummary(events);
        if (!sum.totalEvents) return '';

        const rows = sum.details.length
            ? sum.details.map((item) => `
                <div class="plugin-ai-execution-detail-row${item.copyText ? ' has-copy' : ''}">
                    <strong>${escapeHtml(item.label)}</strong>
                    <span>${escapeHtml(item.value)}</span>
                    ${item.copyText ? `<button type="button" class="plugin-ai-copy-btn plugin-ai-copy-btn--inline" data-copy-text="${escHtmlAttr(item.copyText)}">Copy</button>` : ''}
                </div>
            `)
            : [`<div class="plugin-ai-execution-detail-row"><strong>Execution details</strong><span>No execution events were captured for this run.</span></div>`];

        return `
            <section class="plugin-ai-execution-summary${expanded ? ' is-expanded' : ''}">
                <div class="plugin-ai-execution-summary-head">
                    <div>
                        <strong>Execution summary</strong>
                        <p>${escapeHtml(sum.agents.length)} agent • ${escapeHtml(sum.tools.length)} tool • ${escapeHtml(String(sum.bashCount))} bash</p>
                    </div>
                    <button type="button" class="plugin-ai-inline-toggle" data-plugin-ai-toggle="summaryExpanded">${expanded ? 'Hide details' : 'View details'}</button>
                </div>
                <div class="plugin-ai-summary-chips">
                    <span class="plugin-ai-summary-chip">${escapeHtml(String(sum.totalEvents))} events</span>
                    ${sum.agents.length > 1 ? sum.agents.slice(0, 3).map((agent) => `<span class="plugin-ai-summary-chip">${escapeHtml(agent)}</span>`).join('') : ''}
                    ${sum.tools.slice(0, 3).map((tool) => `<span class="plugin-ai-summary-chip">${escapeHtml(tool)}</span>`).join('')}
                </div>
                ${expanded ? `<div class="plugin-ai-execution-summary-details">${rows.join('')}</div>` : ''}
                ${renderTrace(events)}
            </section>
        `;
    }

    function bindToggles(box) {
        if (!box || box.dataset.inlineTogglesBound === '1') return;
        box.addEventListener('click', async (event) => {
            const copyBtn = event.target.closest('[data-copy-text]');
            if (copyBtn) {
                const text = String(copyBtn.getAttribute('data-copy-text') || '').trim();
                const defAttr = String(copyBtn.getAttribute('data-copy-label') || '').trim();
                if (!copyBtn.dataset.copyDefaultLabel) {
                    copyBtn.dataset.copyDefaultLabel = defAttr || String(copyBtn.textContent || '').trim() || 'Copy';
                }
                const fb = String(copyBtn.dataset.copyDefaultLabel || 'Copy').trim() || 'Copy';
                if (text) {
                    try {
                        if (navigator?.clipboard?.writeText) {
                            await navigator.clipboard.writeText(text);
                        }
                        copyBtn.textContent = defAttr ? '✓' : 'Copied';
                        window.setTimeout(() => {
                            copyBtn.textContent = fb;
                        }, 1200);
                    } catch (_) {
                        copyBtn.textContent = defAttr ? '⚠' : 'Copy failed';
                        window.setTimeout(() => {
                            copyBtn.textContent = fb;
                        }, 1400);
                    }
                }
                return;
            }

            const btn = event.target.closest('[data-plugin-ai-toggle]');
            if (!btn) return;
            const key = String(btn.getAttribute('data-plugin-ai-toggle') || '').trim();
            if (!key || typeof window.togglePluginAiUiFlag !== 'function') return;
            window.togglePluginAiUiFlag(key);
            refreshUi();
        });
        box.dataset.inlineTogglesBound = '1';
    }

    function renderMsgs(msgs = []) {
        const box = document.getElementById('plugin-ai-messages');
        if (!box) return;

        const state = window.getPluginAiState();
        const ui = typeof window.ensurePluginAiUiState === 'function'
            ? window.ensurePluginAiUiState()
            : { activityExpanded: false, summaryExpanded: false };
        const entries = buildActivity(state.liveActivity || state.events || [], state.liveActivityOptions || {});
        const dist = Math.max(0, box.scrollHeight - box.scrollTop - box.clientHeight);
        const stick = dist <= 40;

        if (!Array.isArray(msgs) || msgs.length === 0) {
            box.innerHTML = '';
            box.dataset.renderSignature = '';
            return;
        }

        bindToggles(box);

        const lastBotIdx = [...msgs].map((msg, idx) => ({ msg, idx })).reverse().find((item) => String(item.msg?.role || 'assistant') !== 'user' && !item.msg?.is_pending_assistant)?.idx ?? -1;

        const html = msgs
            .map((msg, idx) => {
                const role = String(msg.role || 'assistant');
                const who = role === 'user' ? 'You' : 'AI';
                const pending = !!msg.is_pending_assistant;
                const cls = `${role === 'user' ? ' is-user' : ''}${pending ? ' is-pending' : ''}`;
                const content = pending ? '' : String(msg.content || '');
                const cachedSnap = pending && typeof window.getPluginAiEventsSnapshot === 'function'
                    ? window.getPluginAiEventsSnapshot(state.plugin, state.threadId, !!state.isTheme)
                    : null;
                const cached = pending && Array.isArray(cachedSnap?.events)
                    ? buildActivity(cachedSnap.events, state.liveActivityOptions || {})
                    : [];
                const live = entries.length ? entries : cached;
                const body = pending
                    ? `
                        ${live.length
                            ? renderRail(live, { expanded: !!ui.activityExpanded })
                            : `
                            <div class="plugin-ai-live-activity plugin-ai-live-activity--compact" aria-live="polite">
                                <div class="plugin-ai-live-activity-head">
                                    <span class="plugin-ai-live-activity-dots"><i></i><i></i><i></i></span>
                                </div>
                            </div>
                        `}
                        ${state.pendingApproval ? renderApproval(state.pendingApproval, state.events || state.liveActivity || []) : ''}
                    `
                    : `
                        <div class="plugin-ai-markdown">${renderMd(content)}</div>
                        ${role !== 'user' ? renderStruct(msg) : ''}
                        ${role !== 'user' && idx === lastBotIdx ? renderApproval(state.pendingApproval, state.events || state.liveActivity || []) : ''}
                        ${role !== 'user' && idx === lastBotIdx ? renderSummary(state.events || state.liveActivity || [], { expanded: !!ui.summaryExpanded }) : ''}
                    `;
                return `
                    <article class="plugin-ai-message${cls}">
                        <strong>${escapeHtml(who)}</strong>
                        ${body}
                    </article>
                `;
            })
            .join('');

        const sig = JSON.stringify({
            messageCount: msgs.length,
            latestAssistantIndex: lastBotIdx,
            latestMessageId: msgs[msgs.length - 1]?.id || '',
            latestMessageContent: String(msgs[msgs.length - 1]?.content || ''),
            pendingCount: msgs.filter((item) => item?.is_pending_assistant).length,
            eventCount: Array.isArray(state.events) ? state.events.length : 0,
            liveActivityCount: Array.isArray(state.liveActivity) ? state.liveActivity.length : 0,
            activityExpanded: !!ui.activityExpanded,
            summaryExpanded: !!ui.summaryExpanded,
            traceExpanded: !!ui.traceExpanded,
        });

        if (box.dataset.renderSignature !== sig) {
            box.innerHTML = html;
            box.dataset.renderSignature = sig;
        }

        if (stick) {
            box.scrollTop = box.scrollHeight;
        }
    }

    function renderActivity(events = []) {
        return renderRail(buildActivity(events), { expanded: true });
    }

    function refreshUi() {
        const state = window.getPluginAiState();
        renderSrcCard();
        renderMsgs(state.messages || []);
    }

    function bumpThread(tid) {
        const state = window.getPluginAiState();
        const threads = Array.isArray(state.threads) ? state.threads : [];
        const idx = threads.findIndex((item) => Number(item.id || 0) === Number(tid || 0));
        if (idx < 0) return;
        const [thread] = threads.splice(idx, 1);
        thread.updated_at = new Date().toISOString();
        state.threads = [thread, ...threads];
        updateChatUi();
    }

    function replaceThread(thread = {}) {
        const state = window.getPluginAiState();
        const threads = Array.isArray(state.threads) ? [...state.threads] : [];
        const idx = threads.findIndex((item) => Number(item.id || 0) === Number(thread.id || 0));
        if (idx < 0) return;
        threads[idx] = { ...threads[idx], ...thread };
        state.threads = threads;
        updateChatUi();
    }

    function removeThread(tid) {
        const state = window.getPluginAiState();
        const threads = Array.isArray(state.threads) ? state.threads.filter((item) => Number(item.id || 0) !== Number(tid || 0)) : [];
        state.threads = threads;
        updateChatUi();
    }

    window.normalizePluginAiInput = normInput;
    window.sanitizePluginAiMessageInput = cleanInput;
    window.normalizePluginAiMessagesPayload = normMsgs;
    window.extractToolEventsFromMessages = toolEvents;
    window.buildPluginAiActivityEntries = buildActivity;
    window.describeAiActivityEvent = describeEvt;
    window.formatPluginAiActivity = fmtActivity;
    window.extractPluginAiMessages = extractMsgs;
    window.mergePluginAiMessages = mergeMsgs;
    window.capturePluginAiMessages = saveMsgs;
    window.pushPluginAiMessage = pushMsg;
    window.replacePendingAssistantMessage = replaceBot;
    window.removePendingAssistantMessage = dropBot;
    window.capturePluginAiToolAudit = saveAudit;
    window.appendPluginAiLiveActivity = addActivity;
    window.applyPluginAiStreamChunk = applyChunk;
    window.buildPluginAiSessionLabel = chatLabel;
    window.buildPluginAiSessionMeta = chatMeta;
    window.getPluginAiSourceStatus = srcStatus;
    window.renderPluginAiSourceStatusCard = renderSrcCard;
    window.renderInlineMarkdown = inlineMd;
    window.renderPluginAiMarkdown = renderMd;
    window.renderPluginAiSessions = renderChats;
    window.updatePluginAiSessionUi = updateChatUi;
    window.setPluginAiMessagesEmptyView = emptyMsgs;
    window.setPluginAiActivityEmptyView = emptyActivity;
    window.renderPluginAiMessages = renderMsgs;
    window.renderPluginAiActivity = renderActivity;
    window.refreshPluginAiRenderedState = refreshUi;
    window.updatePluginAiThreadsAfterMessage = bumpThread;
    window.replacePluginAiThreadInState = replaceThread;
    window.removePluginAiThreadFromState = removeThread;
})();
