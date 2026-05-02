<template>
  <Transition name="modal">
    <div v-if="profile" class="profile-modal-overlay" @click.self="$emit('close')">
      <div class="profile-modal">
        <div class="modal-header">
          <div class="modal-header-info">
            <div class="modal-name-row">
              <span class="modal-realname">{{ profile.username }}</span>
              <span class="modal-username">@{{ profile.name }}</span>
            </div>
            <span class="modal-profession">{{ profile.profession }}</span>
          </div>
          <button class="close-btn" @click="$emit('close')">×</button>
        </div>

        <div class="modal-body">
          <!-- Basic Info -->
          <div class="modal-info-grid">
            <div class="info-item">
              <span class="info-label">외형 연령</span>
              <span class="info-value">{{ profile.age || '-' }} yrs</span>
            </div>
            <div class="info-item">
              <span class="info-label">외형 성별</span>
              <span class="info-value">{{ { male: 'Male', female: 'Female', other: 'Other' }[profile.gender] || profile.gender }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">Country/Region</span>
              <span class="info-value">{{ profile.country || '-' }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">외형 MBTI</span>
              <span class="info-value mbti">{{ profile.mbti || '-' }}</span>
            </div>
          </div>

          <!-- Bio -->
          <div class="modal-section">
            <span class="section-label">프로필 소개</span>
            <p class="section-bio">{{ profile.bio || 'No bio available' }}</p>
          </div>

          <!-- Interested Topics -->
          <div class="modal-section" v-if="profile.interested_topics?.length">
            <span class="section-label">씨드 연관 토픽</span>
            <div class="topics-grid">
              <span
                v-for="topic in profile.interested_topics"
                :key="topic"
                class="topic-item"
              >{{ topic }}</span>
            </div>
          </div>

          <!-- Detailed Persona -->
          <div class="modal-section" v-if="profile.persona">
            <span class="section-label">프로필 상세 배경</span>

            <!-- Persona Dimensions Overview -->
            <div class="persona-dimensions">
              <div class="dimension-card">
                <span class="dim-title">전체 이벤트 경험</span>
                <span class="dim-desc">이 이벤트에서의 전체 행동 궤적</span>
              </div>
              <div class="dimension-card">
                <span class="dim-title">행동 패턴 프로필</span>
                <span class="dim-desc">경험 요약과 행동 스타일 선호</span>
              </div>
              <div class="dimension-card">
                <span class="dim-title">고유 메모리 각인</span>
                <span class="dim-desc">씨드 기반으로 형성된 메모리</span>
              </div>
              <div class="dimension-card">
                <span class="dim-title">사회 관계 네트워크</span>
                <span class="dim-desc">개별 링크 및 상호작용 그래프</span>
              </div>
            </div>

            <div class="persona-content">
              <p class="section-persona">{{ profile.persona }}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  </Transition>
</template>

<script setup>
defineProps({
  profile: { type: Object, default: null },
})

defineEmits(['close'])
</script>

<style scoped src="./ProfileDetailModal.styles.css"></style>
