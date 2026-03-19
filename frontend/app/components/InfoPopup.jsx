'use client';

import { useState, useRef, useEffect } from 'react';

export default function InfoPopup({ text }) {
    const [open, setOpen] = useState(false);
    const ref = useRef(null);

    useEffect(() => {
        if (!open) return;
        const handleClick = (e) => {
            if (ref.current && !ref.current.contains(e.target)) {
                setOpen(false);
            }
        };
        document.addEventListener('mousedown', handleClick);
        return () => document.removeEventListener('mousedown', handleClick);
    }, [open]);

    return (
        <span className="info-popup-wrapper" ref={ref}>
            <button
                className="info-btn"
                onClick={() => setOpen(!open)}
                title="Info"
            >
                ?
            </button>
            {open && (
                <div className="info-popup">
                    <p>{text}</p>
                </div>
            )}
        </span>
    );
}
