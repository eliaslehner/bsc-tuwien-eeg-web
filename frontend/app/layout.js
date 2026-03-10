import './globals.css';

export const metadata = {
  title: 'Brain Viewer — EEG Electrode Mapping',
  description: 'Interactive 3D brain model with Destrieux atlas region mapping',
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
