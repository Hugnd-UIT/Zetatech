(function() {
    const runtime = window.zetatechRuntime;

    function normTag(tag) {
        const val = String(tag || "").trim();
        if (!val) return "";
        return val.replace(/^v+/i, "");
    }

    function fmtVer(tag) {
        const norm = normTag(tag);
        return norm ? `v${norm}` : "";
    }

    function renderAlert(data) {
        const sidebar = document.getElementById('sidebar');
        if (!data) return;

        const hasLatest = !!(data.latest_version && String(data.latest_version).trim());

        if (data.in_progress) {
            if (sidebar) sidebar.classList.add('has-update');
            return;
        }

        if (data.update_available && hasLatest) {
            if (sidebar) sidebar.classList.add('has-update');
            const ver = fmtVer(data.latest_version) || "NEW";

            if (data.latest_version && runtime.getAnnouncedUpdateVersion() !== data.latest_version) {
                runtime.setAnnouncedUpdateVersion(data.latest_version);
                showToast(
                    `New version detected (${ver}). Open the update card to install it.`,
                    "warn"
                );
            }
            return;
        }

        if (sidebar) sidebar.classList.remove('has-update');
        runtime.setAnnouncedUpdateVersion("");
    }

    async function loadStatus(force = false) {
        try {
            const url = `/api/system/update${force ? "?force=true" : ""}`;
            const res = await fetch(url);
            if (!res.ok) {
                throw new Error("Release check failed");
            }
            const data = await res.json();
            runtime.setSystemStatus(data);
            renderStatus(data);
        } catch (err) {
            console.error("System status refresh failed:", err);
            runtime.setSystemStatus(runtime.getSystemStatus() || null);
        }
    }

    function renderStatus(data) {
        if (!data) return;

        const verEl = document.getElementById("app-version");
        if (verEl && data.current_version) {
            verEl.textContent = `v${data.current_version}`;
        }
        renderAlert(data);

        const callout = document.getElementById("update-callout");
        const btn = document.getElementById("update-action-btn");
        const desc = document.getElementById("update-description");
        const latestEl = document.getElementById("update-latest-version");
        const link = document.getElementById("update-release-link");
        const prog = document.getElementById("update-progress");

        const hasLatest = !!(data.latest_version && String(data.latest_version).trim());
        if (data.update_available && hasLatest) {
            if (callout) callout.hidden = false;
            if (latestEl) {
                latestEl.textContent = fmtVer(data.latest_version) || "New version";
            }
            if (desc) {
                desc.textContent =
                    truncateText(data.release_notes) ||
                    data.message ||
                    "Pull the latest image and rerun the container manually.";
            }
            if (link) {
                link.href = data.release_url || "#";
            }
            if (btn) {
                btn.disabled = false;
                btn.textContent = "COPY UPDATE COMMAND";
            }
        } else if (callout) {
            callout.hidden = true;
        }

        if (prog) {
            prog.hidden = true;
        }

        if (data.last_error && data.last_error !== runtime.getLastSystemErrorMessage()) {
            runtime.setLastSystemErrorMessage(data.last_error);
            showToast(`Update check failed: ${data.last_error}`, "warn");
        }

        if (
            data.last_update_message &&
            data.last_update_message !== runtime.getLastSystemUpdateMessage()
        ) {
            runtime.setLastSystemUpdateMessage(data.last_update_message);
            showToast(data.last_update_message, "success");
        }
    }

    function startPoll() {
        const timer = runtime.getSystemStatusTimer();
        if (timer) {
            clearInterval(timer);
        }

        loadStatus();
        runtime.setSystemStatusTimer(
            setInterval(() => loadStatus(), runtime.getSystemPollInterval())
        );
    }

    async function runUpdate() {
        const status = runtime.getSystemStatus();
        if (!status || !status.update_available) {
            showToast("No newer update is available right now.", "info");
            return;
        }

        const latest = fmtVer(status.latest_version) || "the latest version";
        const msg = `${latest} is available. Zetatech no longer runs host-side update scripts automatically. Do you want to copy the manual Docker update command?`;
        const ok = await window.showConfirm(msg);
        if (!ok) return;

        try {
            const res = await fetch("/api/system/update", {
                method: "POST",
            });
            if (!res.ok) {
                const err = await res.text();
                throw new Error(err || "Update request failed.");
            }

            const data = await res.json();
            const cmd = String(data.update_command || "").trim();
            if (!cmd) {
                showToast(data.message || "Manual update instructions are unavailable right now.", "info");
                return;
            }

            await navigator.clipboard.writeText(cmd);
            showToast(data.message || "Manual Docker update command copied to clipboard.", "success");
            loadStatus(true);
        } catch (err) {
            console.error("Failed to prepare update helper:", err);
            showToast(
                `Failed to prepare manual update instructions: ${err.message || "unknown error"}`,
                "error"
            );
        }
    }

    window.startSystemStatusPolling = startPoll;
    window.initiateSystemUpdate = runUpdate;
})();
