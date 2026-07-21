/* ── Cursor Glow (throttled to 60fps max) ── */
const cursorGlow = document.getElementById('cursorGlow');
if (cursorGlow) {
  let rafPending = false;
  let cx = 0, cy = 0;
  document.addEventListener('mousemove', e => {
    cx = e.clientX; cy = e.clientY;
    if (!rafPending) {
      rafPending = true;
      requestAnimationFrame(() => {
        cursorGlow.style.left = cx + 'px';
        cursorGlow.style.top  = cy + 'px';
        rafPending = false;
      });
    }
  }, { passive: true });
}

/* ── Navbar scroll (throttled) ── */
const nav = document.getElementById('mainNav');
if (nav) {
  let scrollRaf = false;
  window.addEventListener('scroll', () => {
    if (!scrollRaf) {
      scrollRaf = true;
      requestAnimationFrame(() => {
        nav.classList.toggle('nav-scrolled', window.scrollY > 60);
        scrollRaf = false;
      });
    }
  }, { passive: true });
}

/* ── Scroll Reveal ── */
const revealObserver = new IntersectionObserver((entries) => {
  entries.forEach(e => {
    if (e.isIntersecting) {
      e.target.classList.add('revealed');
      revealObserver.unobserve(e.target);
    }
  });
}, { threshold: 0.05, rootMargin: '0px 0px -20px 0px' });
document.querySelectorAll('.reveal-up').forEach(el => revealObserver.observe(el));
// Fallback: reveal anything still hidden after 800ms
setTimeout(() => {
  document.querySelectorAll('.reveal-up:not(.revealed)').forEach(el => el.classList.add('revealed'));
}, 800);

/* ── Particle Canvas ── */
const canvas = document.getElementById('particleCanvas');
if (canvas) {
  const ctx = canvas.getContext('2d');
  let particles = [];

  function resizeCanvas() {
    const hero = canvas.parentElement;
    canvas.width  = hero ? hero.offsetWidth : window.innerWidth;
    canvas.height = hero ? hero.offsetHeight : window.innerHeight;
  }
  resizeCanvas();
  window.addEventListener('resize', resizeCanvas);

  class Particle {
    constructor() { this.reset(); }
    reset() {
      this.x     = Math.random() * canvas.width;
      this.y     = Math.random() * canvas.height;
      this.size  = Math.random() * 2 + 0.5;
      this.speedX = (Math.random() - 0.5) * 0.4;
      this.speedY = (Math.random() - 0.5) * 0.4;
      this.alpha = Math.random() * 0.5 + 0.1;
      this.color = Math.random() > 0.5 ? '215,180,106' : '255,255,255';
    }
    update() {
      this.x += this.speedX;
      this.y += this.speedY;
      if (this.x < 0 || this.x > canvas.width || this.y < 0 || this.y > canvas.height) this.reset();
    }
    draw() {
      ctx.beginPath();
      ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(${this.color},${this.alpha})`;
      ctx.fill();
    }
  }

  for (let i = 0; i < 40; i++) particles.push(new Particle()); // reduced from 80

  function animateParticles() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    particles.forEach(p => { p.update(); p.draw(); });
    requestAnimationFrame(animateParticles);
  }
  animateParticles();
}

/* ── Counter Animation ── */
function animateCounter(el) {
  const target = parseInt(el.dataset.count);
  if (!target) return;
  let current = 0;
  const step = Math.ceil(target / 60);
  const timer = setInterval(() => {
    current += step;
    if (current >= target) { current = target; clearInterval(timer); }
    el.textContent = current + '+';
  }, 25);
}
const counterObserver = new IntersectionObserver((entries) => {
  entries.forEach(e => {
    if (e.isIntersecting) {
      animateCounter(e.target);
      counterObserver.unobserve(e.target);
    }
  });
}, { threshold: 0.5 });
document.querySelectorAll('[data-count]').forEach(el => counterObserver.observe(el));



/* ── Time Chip Selection ── */
const timeChips = document.querySelectorAll('.time-chip');
timeChips.forEach(chip => {
  chip.addEventListener('click', () => {
    timeChips.forEach(c => c.classList.remove('active'));
    chip.classList.add('active');
    const inp = document.getElementById('preferred_time');
    if (inp) inp.value = chip.dataset.time;
  });
});

/* ── Date dropdowns → hidden input ── */
const selDay   = document.getElementById('sel_day');
const selMonth = document.getElementById('sel_month');
const selYear  = document.getElementById('sel_year');
const dateInput = document.getElementById('preferred_date');
function updateDateInput() {
  if (selDay && selMonth && selYear && selDay.value && selMonth.value && selYear.value) {
    dateInput.value = `${selYear.value}-${selMonth.value}-${selDay.value}`;
  } else if (dateInput) {
    dateInput.value = '';
  }
}
if (selDay)   selDay.addEventListener('change', updateDateInput);
if (selMonth) selMonth.addEventListener('change', updateDateInput);
if (selYear)  { selYear.addEventListener('change', updateDateInput); selYear.addEventListener('input', updateDateInput); }

/* ── Service Search ── */
const searchInput = document.getElementById('serviceSearch');
if (searchInput) {
  searchInput.addEventListener('input', () => {
    const q = searchInput.value.toLowerCase();
    document.querySelectorAll('.service-col').forEach(col => {
      const name = col.querySelector('.svc-select-name')?.textContent.toLowerCase() || '';
      col.style.display = name.includes(q) ? '' : 'none';
    });
  });
}

/* ── Category Filter ── */
document.querySelectorAll('.cat-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.cat-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    const cat = btn.dataset.cat;
    document.querySelectorAll('.service-col').forEach(col => {
      col.style.display = (cat === 'all' || col.dataset.cat === cat) ? '' : 'none';
    });
  });
});

/* ── Navbar Hamburger ── */
const toggler = document.querySelector('.navbar-toggler-custom');
const navMenu = document.getElementById('navMenu');
if (toggler && navMenu) {
  toggler.addEventListener('click', () => {
    toggler.classList.toggle('open');
    const bsCollapse = bootstrap.Collapse.getOrCreateInstance(navMenu);
    bsCollapse.toggle();
  });
  navMenu.addEventListener('show.bs.collapse', () => toggler.classList.add('open'));
  navMenu.addEventListener('hide.bs.collapse', () => toggler.classList.remove('open'));
}

/* ── Auto dismiss flash ── */
setTimeout(() => {
  document.querySelectorAll('.flash-alert').forEach(a => {
    a.style.opacity = '0';
    a.style.transform = 'translateX(100%)';
    setTimeout(() => a.remove(), 400);
  });
}, 4000);

/* ── Admin Sidebar Toggle ── */
const sidebarToggle = document.getElementById('sidebarToggle');
if (sidebarToggle) {
  sidebarToggle.addEventListener('click', () => {
    document.querySelector('.admin-sidebar')?.classList.toggle('open');
    document.getElementById('sidebarOverlay')?.classList.toggle('show');
  });
  document.getElementById('sidebarOverlay')?.addEventListener('click', () => {
    document.querySelector('.admin-sidebar')?.classList.remove('open');
    document.getElementById('sidebarOverlay')?.classList.remove('show');
  });
}

/* ── Typewriter hero ── */
(function() {
  const el = document.getElementById('heroTypewriter');
  if (!el) return;
  const words = ['Our Passion', 'Your Confidence', 'Our Craft', 'Your Glow'];
  let wi = 0, ci = 0, deleting = false;
  const cursor = document.createElement('span');
  cursor.className = 'typewriter-cursor';
  el.after(cursor);

  function tick() {
    const word = words[wi];
    if (!deleting) {
      el.textContent = word.slice(0, ++ci);
      if (ci === word.length) { deleting = true; setTimeout(tick, 1800); return; }
    } else {
      el.textContent = word.slice(0, --ci);
      if (ci === 0) { deleting = false; wi = (wi + 1) % words.length; setTimeout(tick, 400); return; }
    }
    setTimeout(tick, deleting ? 55 : 90);
  }
  setTimeout(tick, 1200);
})();

/* ── 3D Tilt on service cards ── */
document.querySelectorAll('.tilt-card').forEach(card => {
  card.addEventListener('mousemove', e => {
    const r = card.getBoundingClientRect();
    const x = (e.clientX - r.left) / r.width  - 0.5;
    const y = (e.clientY - r.top)  / r.height - 0.5;
    card.style.transform = `perspective(600px) rotateY(${x * 12}deg) rotateX(${-y * 12}deg) translateY(-6px)`;
  });
  card.addEventListener('mouseleave', () => {
    card.style.transform = '';
  });
});

/* ── Testimonial auto-scroll carousel ── */
(function() {
  const track = document.getElementById('testimonialTrack');
  const dotsWrap = document.getElementById('testimonialDots');
  if (!track || !dotsWrap) return;

  const slides = track.querySelectorAll('.testimonial-slide');
  const total  = slides.length;
  let current  = 0, timer;

  // figure out how many slides visible at once
  function visibleCount() {
    const w = window.innerWidth;
    if (w >= 1024) return 4;
    if (w >= 768)  return 2;
    return 1;
  }

  // build dots
  const maxDot = total - visibleCount() + 1;
  for (let i = 0; i < Math.max(1, maxDot); i++) {
    const d = document.createElement('span');
    d.className = 't-dot' + (i === 0 ? ' active' : '');
    d.addEventListener('click', () => goTo(i));
    dotsWrap.appendChild(d);
  }

  function goTo(idx) {
    const vc = visibleCount();
    const max = Math.max(0, total - vc);
    current = Math.min(idx, max);
    const pct = (100 / vc) * current;
    track.style.transform = `translateX(-${pct}%)`;
    dotsWrap.querySelectorAll('.t-dot').forEach((d, i) => d.classList.toggle('active', i === current));
    resetTimer();
  }

  function next() { goTo((current + 1) % (Math.max(1, total - visibleCount() + 1))); }

  function resetTimer() {
    clearInterval(timer);
    timer = setInterval(next, 3800);
  }

  resetTimer();
  window.addEventListener('resize', () => goTo(0));
})();
