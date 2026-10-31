import React from 'react';

interface VariantToggleProps {
  currentId: string;
  onSelect: (newId: string) => void;
}

export const VariantToggle: React.FC<VariantToggleProps> = ({ currentId, onSelect }) => {
  const variantOf = (id: string) => id.slice(id.lastIndexOf('-') + 1);
  const sibling = (v: string) => currentId.slice(0, currentId.lastIndexOf('-') + 1) + v;
  const currentVariant = variantOf(currentId);

  return (
    <div className="seg-group" role="group" aria-label="Application variant">
      <button
        type="button"
        className="seg"
        aria-pressed={currentVariant === 'seeded'}
        onClick={() => onSelect(sibling('seeded'))}
      >
        Seeded-defect app
      </button>
      <button
        type="button"
        className="seg"
        aria-pressed={currentVariant === 'clean'}
        onClick={() => onSelect(sibling('clean'))}
      >
        Clean control app
      </button>
    </div>
  );
};

