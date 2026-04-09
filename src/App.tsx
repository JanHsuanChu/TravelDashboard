function App() {
  return (
    <div className="app">
      <header className="header">
        <h1>Travel Dashboard</h1>
        <p className="tagline">Plan trips, track places, and see everything in one place.</p>
      </header>
      <main className="grid">
        <section className="card">
          <h2>Upcoming</h2>
          <p className="muted">No trips yet — add your first itinerary.</p>
        </section>
        <section className="card">
          <h2>Places</h2>
          <p className="muted">Saved destinations will appear here.</p>
        </section>
        <section className="card">
          <h2>Notes</h2>
          <p className="muted">Quick travel notes and links.</p>
        </section>
      </main>
    </div>
  );
}

export default App;
