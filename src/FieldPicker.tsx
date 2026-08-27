import { useEffect, useMemo, useState } from "react";
import { Check, Search, X } from "lucide-react";
import type { FieldGroup } from "./api";

const number = new Intl.NumberFormat("uz-UZ");

type Props = {
  groups: FieldGroup[];
  selected: string[];
  onApply: (fields: string[]) => void;
  onClose: () => void;
};

export default function FieldPicker({ groups, selected, onApply, onClose }: Props) {
  const [draft, setDraft] = useState<string[]>(selected);
  const [needle, setNeedle] = useState("");

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const query = needle.trim().toLocaleLowerCase("uz");
  const visible = useMemo(() => {
    if (!query) return groups;
    return groups
      .map((group) => ({
        ...group,
        fields: group.group.toLocaleLowerCase("uz").includes(query)
          ? group.fields
          : group.fields.filter((item) => item.name.toLocaleLowerCase("uz").includes(query)),
      }))
      .filter((group) => group.fields.length > 0);
  }, [groups, query]);

  const draftSet = useMemo(() => new Set(draft), [draft]);
  const toggleField = (name: string) => {
    setDraft((current) => current.includes(name) ? current.filter((item) => item !== name) : [...current, name]);
  };
  const toggleGroup = (group: FieldGroup) => {
    const names = group.fields.map((item) => item.name);
    const allOn = names.every((name) => draftSet.has(name));
    setDraft((current) => allOn
      ? current.filter((item) => !names.includes(item))
      : Array.from(new Set([...current, ...names])));
  };

  return (
    <div className="picker-backdrop" role="dialog" aria-modal="true" aria-label="Fan yo‘nalishini tanlang" onMouseDown={onClose}>
      <div className="picker" onMouseDown={(event) => event.stopPropagation()}>
        <header className="picker-head">
          <h2>Fan yo‘nalishini tanlang</h2>
          <div className="picker-search">
            <Search size={15} />
            <input
              value={needle}
              onChange={(event) => setNeedle(event.target.value)}
              placeholder="Soha nomi bo‘yicha izlash..."
              autoFocus
            />
          </div>
          <button className="picker-close" onClick={onClose} aria-label="Yopish"><X size={18} /></button>
        </header>

        <div className="picker-body">
          {visible.length === 0 && <p className="picker-empty">“{needle}” bo‘yicha soha topilmadi.</p>}
          {visible.map((group) => {
            const names = group.fields.map((item) => item.name);
            const allOn = names.every((name) => draftSet.has(name));
            const someOn = !allOn && names.some((name) => draftSet.has(name));
            return (
              <section className="picker-group" key={group.group}>
                <label className="picker-group-head">
                  <input
                    type="checkbox"
                    checked={allOn}
                    ref={(node) => { if (node) node.indeterminate = someOn; }}
                    onChange={() => toggleGroup(group)}
                  />
                  <strong>{group.group}</strong>
                  <small>{number.format(group.articles)}</small>
                </label>
                <ul>
                  {group.fields.map((item) => (
                    <li key={item.name}>
                      <label>
                        <input
                          type="checkbox"
                          checked={draftSet.has(item.name)}
                          onChange={() => toggleField(item.name)}
                        />
                        <span>{item.name}</span>
                        <small>{number.format(item.articles)}</small>
                      </label>
                    </li>
                  ))}
                </ul>
              </section>
            );
          })}
        </div>

        <footer className="picker-foot">
          <span>{draft.length ? `${draft.length} ta soha tanlandi` : "Soha tanlanmagan — hammasi ko‘rsatiladi"}</span>
          <div>
            <button className="picker-clear" onClick={() => setDraft([])} disabled={draft.length === 0}>Tozalash</button>
            <button className="picker-ok" onClick={() => onApply(draft)}><Check size={15} /> Qo‘llash</button>
          </div>
        </footer>
      </div>
    </div>
  );
}
