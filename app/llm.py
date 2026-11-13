"""Wrapper Groq : modèles configurables, découverte automatique des modèles disponibles,
bascule automatique si un modèle est retiré (404 / decommissioned)."""
import time

from . import config

EXCLUDE = ("whisper", "guard", "tts", "orpheus", "playai", "embed", "safeguard", "distil-whisper")


def _is_gone(err: Exception) -> bool:
    s = str(err).lower()
    return any(k in s for k in ("model_not_found", "does not exist", "decommissioned",
                                "no longer supported", "error code: 404"))


class LLM:
    def __init__(self, api_key=None, model=None, fallback=None):
        from groq import Groq  # import tardif : les tests n'en ont pas besoin

        key = api_key or config.GROQ_API_KEY
        if not key:
            raise RuntimeError("GROQ_API_KEY manquante. Copie .env.example vers .env et renseigne ta clé.")
        self.client = Groq(api_key=key)
        self.model = model or config.MODEL
        self.fallback = fallback or config.FALLBACK_MODEL
        self.dead = set()
        self._discovered = None

    def available_models(self):
        """Modèles de chat réellement accessibles avec ta clé (appel /models)."""
        if self._discovered is None:
            try:
                ids = [m.id for m in self.client.models.list().data]
            except Exception:
                ids = []
            ids = [i for i in ids if not any(x in i.lower() for x in EXCLUDE)]
            # priorité : llama grands/versatiles d'abord, puis le reste
            ids.sort(key=lambda i: (0 if "llama" in i.lower() else 1,
                                    0 if ("70b" in i.lower() or "versatile" in i.lower()) else 1, i))
            self._discovered = ids
        return self._discovered

    def _candidates(self, discover):
        order = [self.model, self.fallback]
        if discover:
            order += self.available_models()
        seen, out = set(), []
        for m in order:
            if m and m not in seen and m not in self.dead:
                seen.add(m)
                out.append(m)
        return out

    def chat(self, messages, tools=None, json_mode=False, temperature=0.2):
        errors = []
        for discover in (False, True):  # d'abord les modèles configurés, puis découverte
            for m in self._candidates(discover):
                for attempt in range(2):
                    try:
                        kwargs = dict(model=m, messages=messages, temperature=temperature)
                        if tools:
                            kwargs.update(tools=tools, tool_choice="auto")
                        if json_mode:
                            kwargs["response_format"] = {"type": "json_object"}
                        resp = self.client.chat.completions.create(**kwargs)
                        if m != self.model:
                            self.model = m  # on garde le modèle qui fonctionne
                        return resp.choices[0].message
                    except Exception as e:
                        errors.append(f"{m}: {str(e)[:160]}")
                        if _is_gone(e):
                            self.dead.add(m)
                            break  # inutile de réessayer ce modèle
                        time.sleep(1.5 * (attempt + 1))
        raise RuntimeError("Aucun modèle Groq utilisable.\n" + "\n".join(errors[-6:]))
