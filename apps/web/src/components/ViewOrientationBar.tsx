import type { AnatomyViewId } from "../viewer/sceneController";
import type { StageSubject } from "../viewer/siteRouting";

/**
 * Anatomical view presets overlaid on the 3D viewer (client ask 2026-07-14: make finding the
 * right face of the mouth easy and safe). One click = one named camera view derived from the
 * scan's own geometry — no orbiting hunt, no upside-down surprises on tilted scanner frames.
 * "Left"/"Right" are screen-relative to the Front view (see AnatomyViewId's doc for why they
 * are not labeled by patient side). Pure presentational component: the controller decides
 * whether a frame exists (clicks are a safe no-op on non-arch views like part previews).
 */
const VIEWS: readonly { readonly id: AnatomyViewId; readonly label: string; readonly title: string }[] = [
  { id: "front", label: "Front", title: "Face the front of the mouth" },
  { id: "left", label: "Left", title: "View from the left of the front view" },
  { id: "right", label: "Right", title: "View from the right of the front view" },
  { id: "occlusal", label: "Top", title: "Look straight down at the crowns (occlusal view)" },
];

/**
 * WHAT THE STAGE IS FRAMED ON (client, 2026-07-26: "Main panel needs to be positioned properly
 * to avoid the use to zoom in and find the cap").
 *
 * The four buttons above choose a DIRECTION; these two choose the SUBJECT, and the two compose —
 * pick "This site" then "Top" and you are looking straight down at the cap. That composition is
 * also why this control has to exist at all: the presets re-place the camera at whatever the
 * last remembered framing was, so before this they doubled as the only way back out to the arch.
 * The moment the remembered subject can be a 6 mm cap that escape route is gone unless it is
 * replaced — which is why the toggle ships with the routing rather than after it.
 */
const SUBJECTS: readonly { readonly id: StageSubject; readonly label: string; readonly title: string }[] = [
  {
    id: "site",
    label: "◎ This site",
    title:
      "Frame the marked cap and its immediate neighbours. The view follows the site you are " +
      "working on — and never moves while you are painting, marking or picking points.",
  },
  {
    id: "arch",
    label: "⊞ Whole arch",
    title: "Back out to the whole jaw. The view then stays where you put it.",
  },
];

interface ViewOrientationBarProps {
  readonly onSelect: (view: AnatomyViewId) => void;
  /** What the stage is currently framed on. Omitted, the subject row is not rendered. */
  readonly subject?: StageSubject;
  readonly onSelectSubject?: (subject: StageSubject) => void;
  /** False when there is no site to frame — "This site" goes down rather than doing nothing. */
  readonly siteAvailable?: boolean;
}

export function ViewOrientationBar({
  onSelect,
  subject,
  onSelectSubject,
  siteAvailable = false,
}: ViewOrientationBarProps) {
  return (
    <div className="view-orient" role="group" aria-label="Camera views">
      <div className="view-orient__row" role="group" aria-label="Anatomical view presets">
        {VIEWS.map((view) => (
          <button
            key={view.id}
            type="button"
            className="view-orient__button"
            title={view.title}
            onClick={() => onSelect(view.id)}
          >
            {view.label}
          </button>
        ))}
      </div>
      {subject && onSelectSubject && (
        <div className="view-orient__row" role="group" aria-label="What the view is framed on">
          {SUBJECTS.map((choice) => (
            <button
              key={choice.id}
              type="button"
              className={`view-orient__button${
                choice.id === subject ? " view-orient__button--active" : ""
              }`}
              aria-pressed={choice.id === subject}
              disabled={choice.id === "site" && !siteAvailable}
              title={
                choice.id === "site" && !siteAvailable
                  ? "Mark a cap first — there is no site to frame yet"
                  : choice.title
              }
              onClick={() => onSelectSubject(choice.id)}
            >
              {choice.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
