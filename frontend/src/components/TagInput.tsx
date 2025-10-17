import { KeyboardEvent, useState } from 'react';

type TagInputProps = {
  value: string[];
  onChange: (value: string[]) => void;
  placeholder?: string;
};

const TagInput = ({ value, onChange, placeholder }: TagInputProps) => {
  const [inputValue, setInputValue] = useState('');

  const commitValue = () => {
    const trimmed = inputValue.trim();
    if (!trimmed) {
      setInputValue('');
      return;
    }
    if (value.includes(trimmed)) {
      setInputValue('');
      return;
    }
    onChange([...value, trimmed]);
    setInputValue('');
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter' || event.key === ',') {
      event.preventDefault();
      commitValue();
    } else if (event.key === 'Backspace' && !inputValue) {
      onChange(value.slice(0, Math.max(0, value.length - 1)));
    }
  };

  const removeTag = (tag: string) => {
    onChange(value.filter((item) => item !== tag));
  };

  return (
    <div className="tag-input">
      {value.map((tag) => (
        <span key={tag} className="tag">
          {tag}
          <button type="button" onClick={() => removeTag(tag)} aria-label={`Remove ${tag}`}>
            ×
          </button>
        </span>
      ))}
      <input
        value={inputValue}
        onChange={(event) => setInputValue(event.target.value)}
        onKeyDown={handleKeyDown}
        onBlur={commitValue}
        placeholder={placeholder}
      />
    </div>
  );
};

export default TagInput;
