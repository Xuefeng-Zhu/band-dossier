import {api, key, Refusal} from "./api.js";
import {notice} from "./ui.js";

// Only a definite response releases the key. The pending envelope includes the
// original, serialized body so retries survive import or competing clients.
export function writer(action, getRequest, submit, feedback, onSuccess) {
  let pending = null;
  let sending = false;
  return async () => {
    if (sending) return;
    if (!pending) pending = {...getRequest(), key:key()};
    sending = true;
    submit.disabled = true;
    submit.setAttribute("aria-busy","true");
    feedback.replaceChildren();
    try {
      const reply = await api(pending.path, {
        method:"POST", headers:{"Idempotency-Key":pending.key}, body:pending.body
      });
      if (!reply?.domain || !reply?.dossier_id) throw new Error("Incomplete response");
      pending = null;
      await onSuccess(reply);
    } catch (err) {
      if (err instanceof Refusal) {
        pending = null;
        notice(feedback, "error", action + "-error", err.message);
      } else {
        notice(feedback, "uncertain", action + "-uncertain",
          "The response was lost. Use " + (action === "refresh" ? "Refresh" : "Research") +
          " again to retry the original request.");
      }
    } finally {
      sending = false;
      submit.disabled = false;
      submit.removeAttribute("aria-busy");
    }
  };
}
