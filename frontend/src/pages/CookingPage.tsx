import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import {
  getCookingCapabilities, getConversation, listConversations, sendChat,
} from "../api/endpoints";
import type { ChatMessage, ConversationSummary, Recipe } from "../api/types";
import { FormError, errorMessage } from "../components/FormError";
import { RecipeView } from "../components/cooking/RecipeView";
import { useToast } from "../components/Toast";
import { Card, ErrorState, Loading, PageHeader } from "../components/ui";
import { useResource } from "../hooks/useResource";
import { formatDate } from "../lib/format";

interface LocalMessage extends ChatMessage { pending?: boolean }

export function CookingPage() {
  const toast = useToast();
  const caps = useResource(useCallback(() => getCookingCapabilities(), []));
  const list = useResource(useCallback(() => listConversations(1), []));
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<LocalMessage[]>([]);
  const [recipes, setRecipes] = useState<Recipe[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async (id: string) => {
    const d = await getConversation(id);
    setConversationId(id);
    setMessages(d.messages as LocalMessage[]);
    // Fetch each referenced recipe (cheap, and lets us render its full detail)
    const recipeIds = Array.from(new Set(d.messages.map((m) => m.recipe_id).filter(Boolean) as string[]));
    const loaded = await Promise.all(recipeIds.map((rid) => import("../api/endpoints").then((m) => m.getRecipe(rid))));
    setRecipes(loaded);
    list.reload();
  }, [list]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages]);

  async function send(e: FormEvent) {
    e.preventDefault();
    const text = draft.trim();
    if (!text) return;
    setError(null);
    setDraft("");
    const local: LocalMessage = {
      id: `local-${Date.now()}`, role: "user", content: text,
      recipe_id: null, warnings: [], created_at: new Date().toISOString(),
    };
    setMessages((m) => [...m, local]);
    setBusy(true);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const res = await sendChat(text, conversationId, controller.signal);
      setConversationId(res.conversation_id);
      setMessages((m) => [
        ...m.filter((x) => x.id !== local.id),
        res.user_message,
        res.assistant_message,
      ]);
      if (res.recipe) setRecipes((r) => [...r, res.recipe!]);
      list.reload();
    } catch (err) {
      setMessages((m) => m.filter((x) => x.id !== local.id));
      if (!(err instanceof DOMException && err.name === "AbortError")) {
        setError(errorMessage(err));
      }
    } finally {
      abortRef.current = null;
      setBusy(false);
    }
  }

  if (caps.error) return <ErrorState error={caps.error} onRetry={caps.reload} />;
  if (!caps.data) return <Loading />;
  const { text } = caps.data;

  return (
    <>
      <PageHeader
        title="Cooking assistant"
        description="Recipes, substitutions, and step-by-step help that respect your allergies and diet."
        actions={<Link className="button-link secondary" to="/recipes">All saved recipes</Link>}
      />
      {!text.configured && (
        <p className="alert info" role="note">
          The cooking assistant is not available: {text.message} Your saved recipes below still work.
        </p>
      )}
      {text.configured && text.external && (
        <p className="alert warn" role="note">
          Your messages will be sent to an external service ({text.provider}) that the server operator enabled.
        </p>
      )}
      {text.configured && (
        <p className="small-text muted">{caps.data.context_note}</p>
      )}

      <div className="cooking-layout">
        <Card title="Conversations" headingId="conv-heading">
          {list.error ? (
            <ErrorState error={list.error} onRetry={list.reload} />
          ) : !list.data ? (
            <Loading />
          ) : list.data.items.length === 0 ? (
            <p className="muted small-text">No conversations yet.</p>
          ) : (
            <ul className="conversation-list">
              {list.data.items.map((c: ConversationSummary) => (
                <li key={c.id}>
                  <button
                    type="button"
                    className={c.id === conversationId ? "conversation-active" : ""}
                    onClick={() => { void load(c.id); }}
                  >
                    <span className="conversation-title">{c.title}</span>
                    <span className="muted small-text">
                      {c.message_count} · {formatDate(c.updated_at)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          {conversationId && (
            <button
              type="button"
              className="secondary small"
              onClick={() => { setConversationId(null); setMessages([]); setRecipes([]); }}
            >
              New conversation
            </button>
          )}
        </Card>

        <Card title={conversationId ? "Conversation" : "Ask anything"} headingId="chat-heading">
          <div ref={scrollRef} className="chat-scroll" aria-live="polite">
            {messages.length === 0 && (
              <p className="muted">
                Ask for a recipe, a substitution, or a beginner-friendly explanation. For example:
                “What can I cook with rice, lemon and salt?”
              </p>
            )}
            {messages.map((m) => (
              <div key={m.id} className={`chat-turn chat-${m.role}`}>
                <p className="chat-role">{m.role === "user" ? "You" : "Assistant"}</p>
                <p className="chat-body" style={{ whiteSpace: "pre-wrap" }}>{m.content}</p>
                {m.warnings.length > 0 && (
                  <ul className="chat-warnings small-text">
                    {m.warnings.map((w, i) => <li key={i}>{w}</li>)}
                  </ul>
                )}
              </div>
            ))}
            {busy && (
              <div className="loading" role="status" aria-live="polite">
                <span className="spinner" aria-hidden="true" />
                <span>Waiting for the assistant…</span>
                <button type="button" className="secondary small" onClick={() => abortRef.current?.abort()}>
                  Cancel
                </button>
              </div>
            )}
          </div>
          <FormError message={error} />
          <form onSubmit={send} noValidate>
            <label htmlFor="chat-input" className="visually-hidden">Message</label>
            <textarea
              id="chat-input"
              rows={3}
              maxLength={2000}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              disabled={busy || !text.configured}
              placeholder={text.configured ? "Ask the assistant…" : "Configure a text model to use the assistant."}
            />
            <button type="submit" disabled={busy || !draft.trim() || !text.configured}>
              {busy ? "Sending…" : "Send"}
            </button>
          </form>
        </Card>
      </div>

      {recipes.map((r) => (
        <RecipeView key={r.id} recipe={r} onSaved={(next) => setRecipes(
          (all) => all.map((x) => (x.id === next.id ? next : x)),
        )} onDeleted={() => setRecipes((all) => all.filter((x) => x.id !== r.id))} />
      ))}
      {recipes.length > 0 && toast && null /* toasts render themselves */}
    </>
  );
}