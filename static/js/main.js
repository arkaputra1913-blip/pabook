document.addEventListener('DOMContentLoaded', () => {

  // ── Count-up animation ──
  document.querySelectorAll('.count-up').forEach(el => {
    const target = parseInt(el.textContent) || 0;
    if (target === 0) return;
    let cur = 0;
    const inc = Math.max(1, Math.ceil(target / 30));
    const t = setInterval(() => {
      cur = Math.min(cur + inc, target);
      el.textContent = cur;
      if (cur >= target) clearInterval(t);
    }, 40);
  });

  // ── Staggered card animation ──
  document.querySelectorAll('.card, .booking-panel, .ticket-card, .gate-card').forEach((el, i) => {
    el.style.animationDelay = `${i * 0.07}s`;
  });

  // ── Active nav highlight ──
  const path = window.location.pathname;
  document.querySelectorAll('.nav-item').forEach(a => {
    if (a.getAttribute('href') === path) a.classList.add('active');
  });

  // ── Slot shake on occupied click attempt ──
  document.querySelectorAll('.slot-btn.occupied, .slot-btn.reserved').forEach(btn => {
    btn.addEventListener('click', () => {
      btn.style.transform = 'translateX(-4px)';
      setTimeout(() => btn.style.transform = 'translateX(4px)', 80);
      setTimeout(() => btn.style.transform = 'translateX(0)', 160);
    });
  });

});