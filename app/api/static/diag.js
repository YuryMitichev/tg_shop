(function () {
    "use strict";

    window.__errs = [];
    window.addEventListener("error", function (event) {
        try {
            window.__errs.push(
                (event.message || "unknown") + "@" +
                (event.filename || "").split("/").pop() + ":" +
                (event.lineno || 0) + ":" + (event.colno || 0)
            );
        } catch (_) { }
    });
    window.addEventListener("unhandledrejection", function (event) {
        try {
            var reason = event.reason;
            window.__errs.push("PROMISE:" + (reason && reason.message ? reason.message : String(reason)));
        } catch (_) { }
    });
    window.addEventListener("load", function () {
        try {
            var query = [];
            query.push("app=" + (typeof window.App));
            query.push("tg=" + (window.Telegram && window.Telegram.WebApp ? "1" : "none"));
            query.push("fetch=" + (typeof window.fetch));
            query.push("json=" + (typeof window.JSON));
            query.push("e=" + encodeURIComponent(window.__errs.join(" | ").substring(0, 300)));
            var image = new Image();
            image.src = "/app/__diag?" + query.join("&");
        } catch (_) { }
    });
})();
