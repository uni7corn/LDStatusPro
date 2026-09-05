<template>
  <div class="support-page">
    <div class="support-container">
      <router-link to="/" class="support-back">← 返回首页</router-link>

      <section class="support-hero">
        <svg class="support-hero-watermark" viewBox="0 0 24 24" aria-hidden="true">
          <path
            d="M12 21l-1.4-1.3C5.4 15.4 2 12.3 2 8.5 2 5.4 4.4 3 7.5 3c1.7 0 3.4.8 4.5 2.1C13.1 3.8 14.8 3 16.5 3 19.6 3 22 5.4 22 8.5c0 3.8-3.4 6.9-8.6 11.5L12 21z"
            fill="currentColor"
          />
        </svg>
        <div class="support-hero-title">
          <span class="support-heart">💖</span>
          支持 LD士多
        </div>
        <p class="support-hero-desc">
          感谢您使用 🍔LD士多！<br />
          您的支持是我持续开发的动力
        </p>
        <div class="support-hero-points">
          <span class="support-point">服务器维护</span>
          <span class="support-point">功能开发</span>
          <span class="support-point">社区共建</span>
        </div>
      </section>

      <a
        class="support-github-card"
        href="https://github.com/caigg188/LDStatusPro"
        target="_blank"
        rel="noopener"
      >
        <div class="github-icon-wrap">
          <svg class="github-icon" viewBox="0 0 98 96" aria-hidden="true">
            <path
              fill-rule="evenodd"
              clip-rule="evenodd"
              d="M48.854 0C21.839 0 0 22 0 49.217c0 21.756 13.993 40.172 33.405 46.69 2.427.49 3.316-1.059 3.316-2.362 0-1.141-.08-5.052-.08-9.127-13.59 2.934-16.42-5.867-16.42-5.867-2.184-5.704-5.42-7.17-5.42-7.17-4.448-3.015.324-3.015.324-3.015 4.934.326 7.523 5.052 7.523 5.052 4.367 7.496 11.404 5.378 14.235 4.074.404-3.178 1.699-5.378 3.074-6.6-10.839-1.141-22.243-5.378-22.243-24.283 0-5.378 1.94-9.778 5.014-13.2-.485-1.222-2.184-6.275.486-13.038 0 0 4.125-1.304 13.426 5.052a46.97 46.97 0 0 1 12.214-1.63c4.125 0 8.33.571 12.213 1.63 9.302-6.356 13.427-5.052 13.427-5.052 2.67 6.763.97 11.816.485 13.038 3.155 3.422 5.015 7.822 5.015 13.2 0 18.905-11.404 23.06-22.324 24.283 1.78 1.548 3.316 4.481 3.316 9.126 0 6.6-.08 11.897-.08 13.526 0 1.304.89 2.853 3.316 2.364 19.412-6.52 33.405-24.935 33.405-46.691C97.707 22 75.788 0 48.854 0z"
            />
          </svg>
        </div>
        <div class="github-content">
          <div class="github-title">
            在 GitHub 上 Star 一下 <span class="github-star-icon">⭐️</span>
          </div>
          <div class="github-desc">您的 Star 是对作者最好的鼓励</div>
        </div>
        <span class="github-arrow">→</span>
      </a>

      <div class="support-grid">
        <a
          v-for="tier in supportTiers"
          :key="tier.id"
          :href="tier.url"
          target="_blank"
          rel="noopener"
          :class="['support-card', `tier-${tier.id}`]"
        >
          <span v-if="tier.badge" class="support-badge">{{ tier.badge }}</span>
          <div class="support-icon">{{ tier.icon }}</div>
          <div class="support-name">{{ tier.name }}</div>
          <div class="support-amount">
            {{ tier.amount }} <span>LDC</span>
          </div>
        </a>
      </div>

      <div class="support-footer">
        <div class="support-footer-text">
          🙏 每一份支持都将用于<em>服务器维护</em>和<em>功能开发</em><br />
          感谢社区每一位用户的信任与陪伴
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
const supportTiers = [
  {
    id: 1,
    name: '大力支持',
    amount: 10,
    icon: '🚀',
    // badge: '热门',
    url: 'https://credit.linux.do/paying/online?token=8f4f08c0ceb719c922d105a3be4c2d6d890aa17b47b73fa756510aa1abdc1bf7'
  },
  {
    id: 2,
    name: '深得我心',
    amount: 25,
    icon: '❤️',
    badge: '火热',
    url: 'https://credit.linux.do/paying/online?token=7a3d6fb647a275b55c248ad58b546e02905f7a05c08579906773bd323c2e2242'
  },
  {
    id: 3,
    name: '社区贡献者',
    amount: 50,
    icon: '👑',
    badge: '尊享',
    url: 'https://credit.linux.do/paying/online?token=78d243962c635d1fe2deaecd2e8c59abf778113d25b1e5d05364c8a586fd5384'
  },
  {
    id: 4,
    name: '你最棒',
    amount: 100,
    icon: '💎',
    badge: '顶级',
    url: 'https://credit.linux.do/paying/online?token=6628b880f273541ee808beb22934aac11378175dd7fab4e6ce8694a846627e21'
  }
]
</script>

<style scoped>
.support-page {
  position: relative;
  padding: 36px 16px 120px;
  min-height: calc(100vh - 60px);
  overflow: hidden;
}

.support-page::before,
.support-page::after {
  content: '';
  position: absolute;
  width: 320px;
  height: 320px;
  border-radius: 50%;
  background: radial-gradient(circle, var(--palette-rgba-181-168-152-0p18), transparent 70%);
  filter: blur(0px);
  z-index: 0;
}

.support-page::before {
  top: -120px;
  left: -120px;
}

.support-page::after {
  bottom: -140px;
  right: -120px;
}

.support-container {
  max-width: 960px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 22px;
  position: relative;
  z-index: 1;
}

.support-back {
  align-self: flex-start;
  font-size: 13px;
  color: var(--text-tertiary);
  transition: color 0.2s ease;
}

.support-back:hover {
  color: var(--color-primary);
}

.support-hero {
  position: relative;
  padding: 26px 28px;
  border-radius: 26px;
  background:
    radial-gradient(circle at 85% 15%, var(--palette-rgba-239-122-122-0p12), transparent 60%),
    linear-gradient(135deg, var(--palette-rgba-181-168-152-0p25), var(--palette-rgba-255-255-255-0p92));
  border: 1px solid var(--glass-border);
  box-shadow: var(--shadow-lg);
  overflow: hidden;
  isolation: isolate;
  animation: support-rise 0.6s cubic-bezier(0.22, 1, 0.36, 1) both;
}

.support-hero::before {
  content: '';
  position: absolute;
  top: -35%;
  right: -15%;
  width: 220px;
  height: 220px;
  background: radial-gradient(circle, var(--palette-rgba-239-122-122-0p12), transparent 70%);
  opacity: 0.6;
  z-index: 0;
}

.support-hero::after {
  content: '';
  position: absolute;
  inset: 0;
  background: radial-gradient(circle at 15% 15%, var(--palette-rgba-255-255-255-0p5), transparent 45%);
  opacity: 0.7;
  pointer-events: none;
  z-index: 0;
}

.support-hero-title {
  position: relative;
  font-size: 26px;
  font-weight: 700;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
  z-index: 2;
}


.support-hero-watermark {
  position: absolute;
  right: -30px;
  top: -20px;
  width: 220px;
  height: 220px;
  color: var(--palette-rgba-239-122-122-0p16);
  opacity: 0.8;
  filter: drop-shadow(0 12px 24px var(--palette-rgba-239-122-122-0p18));
  transform: rotate(6deg);
  pointer-events: none;
  z-index: 1;
}

.support-heart {
  display: inline-block;
  animation: heart-beat 1.4s ease-in-out infinite;
  filter: drop-shadow(0 0 6px var(--palette-rgba-239-122-122-0p5));
}

.support-hero-desc {
  position: relative;
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.6;
  z-index: 2;
}

.support-hero-points {
  position: relative;
  margin-top: 16px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  z-index: 2;
}

.support-point {
  padding: 6px 12px;
  font-size: 12px;
  border-radius: 999px;
  background: var(--glass-bg-light);
  border: 1px solid var(--glass-border);
  color: var(--text-secondary);
  box-shadow: 0 6px 16px var(--glass-shadow-light);
  backdrop-filter: blur(6px);
}

.support-github-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 18px;
  border-radius: 20px;
  background: var(--glass-bg-heavy);
  border: 1px solid var(--glass-border);
  box-shadow: var(--shadow-md);
  transition: transform 0.3s ease, box-shadow 0.3s ease;
  position: relative;
  overflow: hidden;
  animation: support-rise 0.6s 0.1s cubic-bezier(0.22, 1, 0.36, 1) both;
}

.support-github-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 16px 32px var(--palette-rgba-0-0-0-0p12);
}

.support-github-card::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(120deg, transparent 30%, var(--palette-rgba-255-255-255-0p6), transparent 70%);
  opacity: 0;
  transform: translateX(-30%);
  transition: opacity 0.3s ease, transform 0.6s ease;
}

.support-github-card:hover::after {
  opacity: 0.4;
  transform: translateX(30%);
}

.github-icon-wrap {
  width: 40px;
  height: 40px;
  border-radius: 14px;
  background: var(--bg-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: inset 0 1px 0 var(--palette-rgba-255-255-255-0p6);
}

.github-icon {
  width: 28px;
  height: 28px;
  fill: var(--text-primary);
}

.github-content {
  flex: 1;
}

.github-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 6px;
}

.github-star-icon {
  color: var(--palette-hex-f59e0b);
}

.github-desc {
  font-size: 12px;
  color: var(--text-tertiary);
  margin-top: 4px;
}

.github-arrow {
  font-size: 18px;
  color: var(--text-tertiary);
}

.support-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.support-card {
  position: relative;
  padding: 18px 16px;
  border-radius: 20px;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  transition: transform 0.36s cubic-bezier(0.22, 1, 0.36, 1), box-shadow 0.28s ease, border-color 0.28s ease;
  overflow: hidden;
  animation: support-rise 0.6s cubic-bezier(0.22, 1, 0.36, 1) both;
}

.support-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: linear-gradient(90deg, transparent, var(--accent), transparent);
  opacity: 0.6;
}

.support-card::after {
  content: '';
  position: absolute;
  inset: 0;
  background: radial-gradient(circle at 50% 0%, var(--accent), transparent 70%);
  opacity: 0;
  transition: opacity 0.28s ease;
}

.support-card:hover {
  transform: translateY(-4px) scale(1.02);
  box-shadow: 0 16px 30px var(--glow);
  border-color: color-mix(in srgb, var(--accent) 45%, var(--border-light));
}

.support-card:active {
  transform: translateY(-2px) scale(1.01);
}

.support-card:hover::after {
  opacity: 0.1;
}

.support-icon {
  font-size: 34px;
  filter: drop-shadow(0 6px 12px var(--glow));
  transition: transform 0.3s ease;
}

.support-card:hover .support-icon {
  transform: translateY(-3px) scale(1.05);
}

.support-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: 0.3px;
}

.support-amount {
  font-size: 22px;
  font-weight: 700;
  color: var(--accent);
  display: flex;
  align-items: baseline;
  gap: 4px;
  text-shadow: 0 2px 6px var(--glow);
}

.support-amount span {
  font-size: 11px;
  font-weight: 500;
  color: var(--text-tertiary);
}

.support-badge {
  position: absolute;
  top: 10px;
  right: 10px;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 600;
  color: var(--palette-hex-ffffff);
  background: linear-gradient(135deg, var(--accent), color-mix(in srgb, var(--accent) 70%, var(--palette-hex-000000)));
  box-shadow: 0 6px 14px var(--glow);
  animation: badge-float 3s ease-in-out infinite;
}

.support-card.tier-1 {
  --accent: var(--palette-hex-6fbf8f);
  --glow: var(--palette-rgba-111-191-143-0p25);
}

.support-card.tier-2 {
  --accent: var(--palette-hex-6aa6d9);
  --glow: var(--palette-rgba-106-166-217-0p25);
}

.support-card.tier-3 {
  --accent: var(--palette-hex-f2b561);
  --glow: var(--palette-rgba-242-181-97-0p32);
}

.support-card.tier-4 {
  --accent: var(--palette-hex-ef7a7a);
  --glow: var(--palette-rgba-239-122-122-0p32);
  background: linear-gradient(145deg, var(--bg-card), var(--palette-rgba-239-122-122-0p08));
}

.support-card.tier-3::before,
.support-card.tier-4::before {
  animation: shimmer 2.4s ease-in-out infinite;
}

.support-card:nth-child(1) {
  animation-delay: 0.12s;
}

.support-card:nth-child(2) {
  animation-delay: 0.18s;
}

.support-card:nth-child(3) {
  animation-delay: 0.24s;
}

.support-card:nth-child(4) {
  animation-delay: 0.3s;
}

.support-footer {
  text-align: center;
  padding: 14px 16px;
  border-radius: 18px;
  background: var(--glass-bg-heavy);
  border: 1px solid var(--glass-border);
  box-shadow: var(--shadow-sm);
  animation: support-rise 0.6s 0.18s cubic-bezier(0.22, 1, 0.36, 1) both;
}

.support-footer-text {
  font-size: 12px;
  color: var(--text-tertiary);
  line-height: 1.7;
}

.support-footer-text em {
  font-style: normal;
  color: var(--color-primary);
  font-weight: 600;
}

@keyframes heart-beat {
  0%,
  100% {
    transform: scale(1);
  }
  50% {
    transform: scale(1.12);
  }
}

@keyframes support-rise {
  0% {
    opacity: 0;
    transform: translateY(14px) scale(0.98);
  }
  100% {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

@keyframes badge-float {
  0%,
  100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-4px);
  }
}

@keyframes shimmer {
  0%,
  100% {
    opacity: 0.6;
  }
  50% {
    opacity: 1;
  }
}

@media (max-width: 768px) {
  .support-hero {
    padding: 22px 20px;
  }

  .support-hero-title {
    font-size: 22px;
  }

  .support-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 480px) {
  .support-github-card {
    flex-direction: column;
    align-items: flex-start;
  }

  .github-arrow {
    align-self: flex-end;
  }
}

@media (prefers-reduced-motion: reduce) {
  .support-heart,
  .support-badge,
  .support-card::before,
  .support-hero,
  .support-github-card,
  .support-card,
  .support-footer {
    animation: none;
  }

  .support-github-card::after {
    transition: none;
  }
}
</style>
