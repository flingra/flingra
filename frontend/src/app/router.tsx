import { Route, Routes } from 'react-router-dom'
import { ShellLayout } from './layouts/shell-layout'
import { OnboardingLayout } from './layouts/onboarding-layout'
import { ProtectedRoute, PublicOnlyRoute } from './protected-route'
import { NotFound } from './not-found'

import { LandingPage } from '@/features/marketing/landing-page'
import { SignUpPage } from '@/features/auth/pages/signup-page'
import { LoginPage } from '@/features/auth/pages/login-page'
import { VerifyContactPage } from '@/features/auth/pages/verify-contact-page'
import { ForgotPasswordPage } from '@/features/auth/pages/forgot-password-page'
import { ResetPasswordPage } from '@/features/auth/pages/reset-password-page'
import { TermsPage } from '@/features/legal/terms-page'
import { PrivacyPage as LegalPrivacyPage } from '@/features/legal/privacy-page'
import { OnboardingPage } from '@/features/onboarding/pages/onboarding-page'
import { DiscoverPage } from '@/features/discovery/pages/discover-page'
import { ProfileDetailPage } from '@/features/discovery/pages/profile-detail-page'
import { ChatPage } from '@/features/messages/pages/chat-page'
import { EditProfilePage } from '@/features/profile/pages/edit-profile-page'
import { SettingsPage } from '@/features/settings/pages/settings-page'
import { VerificationPage } from '@/features/settings/pages/verification-page'
import { SecurityPage } from '@/features/settings/pages/security-page'
import { PrivacyPage as SettingsPrivacyPage } from '@/features/settings/pages/privacy-page'
import { SafetyPage } from '@/features/safety/pages/safety-page'
import { HelpPage } from '@/features/safety/pages/help-page'
import { BlockedPage } from '@/features/safety/pages/blocked-page'
import { EmergencyContactsPage } from '@/features/safety/pages/emergency-contacts-page'
import { StatusPage } from '@/features/status/pages/status-page'
import { LivePage } from '@/features/livestream/pages/live-page'
import { LivestreamsPage } from '@/features/livestream/pages/livestreams-page'
import { VipPage } from '@/features/subscription/pages/vip-page'
import { WalletPage } from '@/features/wallet/pages/wallet-page'
import { GiftShopPage } from '@/features/wallet/pages/gift-shop-page'
import { RedeemGiftsPage } from '@/features/wallet/pages/redeem-gifts-page'
import { ReferralsPage } from '@/features/wallet/pages/referrals-page'
import { PayoutPage } from '@/features/wallet/pages/payout-page'
import { CreditStorePage } from '@/features/wallet/pages/credit-store-page'
import { AdminRoute } from '@/features/admin/admin-route'
import { AdminLayout } from '@/features/admin/admin-layout'
import { AdminAccountsPage, AdminAuditPage, AdminLoginPage, AdminReviewsPage } from '@/features/admin/admin-pages'
import { AdminCoinPricingPage } from '@/features/admin/pages/admin-coin-pricing-page'

export function AppRouter() {
  return (
    <Routes>
      <Route element={<ShellLayout />}>
        <Route index element={<LandingPage />} />
        <Route
          path="signup"
          element={
            <PublicOnlyRoute>
              <SignUpPage />
            </PublicOnlyRoute>
          }
        />
        <Route
          path="login"
          element={
            <PublicOnlyRoute>
              <LoginPage />
            </PublicOnlyRoute>
          }
        />
        <Route
          path="verify-contact"
          element={
            <ProtectedRoute allow={['needs-verification']}>
              <VerifyContactPage />
            </ProtectedRoute>
          }
        />
        <Route path="password/forgot" element={<ForgotPasswordPage />} />
        <Route path="password/reset" element={<ResetPasswordPage />} />
        <Route path="terms" element={<TermsPage />} />
        <Route path="privacy" element={<LegalPrivacyPage />} />
        <Route path="safety" element={<SafetyPage />} />
        <Route path="help" element={<HelpPage />} />

        <Route
          path="discover"
          element={
            <ProtectedRoute allow={['active']}>
              <DiscoverPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="profiles/:profileId"
          element={
            <ProtectedRoute allow={['active']}>
              <ProfileDetailPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="messages/:threadId"
          element={
            <ProtectedRoute allow={['active']}>
              <ChatPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="settings/profile"
          element={
            <ProtectedRoute allow={['active']}>
              <EditProfilePage />
            </ProtectedRoute>
          }
        />
        <Route
          path="settings"
          element={
            <ProtectedRoute allow={['active']}>
              <SettingsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="settings/verification"
          element={
            <ProtectedRoute allow={['active']}>
              <VerificationPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="settings/security"
          element={
            <ProtectedRoute allow={['active']}>
              <SecurityPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="settings/privacy"
          element={
            <ProtectedRoute allow={['active']}>
              <SettingsPrivacyPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="blocked"
          element={
            <ProtectedRoute allow={['active']}>
              <BlockedPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="safety/emergency-contacts"
          element={
            <ProtectedRoute allow={['active']}>
              <EmergencyContactsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="status"
          element={
            <ProtectedRoute allow={['active']}>
              <StatusPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="live"
          element={
            <ProtectedRoute allow={['active']}>
              <LivestreamsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="vip"
          element={
            <ProtectedRoute allow={['active']}>
              <VipPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="wallet"
          element={
            <ProtectedRoute allow={['active']}>
              <WalletPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="gifts/shop"
          element={
            <ProtectedRoute allow={['active']}>
              <GiftShopPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="gifts/redeem"
          element={
            <ProtectedRoute allow={['active']}>
              <RedeemGiftsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="referrals"
          element={
            <ProtectedRoute allow={['active']}>
              <ReferralsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="payout"
          element={
            <ProtectedRoute allow={['active']}>
              <PayoutPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="credits/shop"
          element={
            <ProtectedRoute allow={['active']}>
              <CreditStorePage />
            </ProtectedRoute>
          }
        />

        <Route path="*" element={<NotFound />} />
      </Route>

      <Route element={<OnboardingLayout />}>
        <Route
          path="onboarding"
          element={
            <ProtectedRoute allow={['needs-onboarding']}>
              <OnboardingPage />
            </ProtectedRoute>
          }
        />
      </Route>

      {/* Full-screen, no header/bottom-nav chrome, like a real livestream takeover. */}
      <Route
        path="live/:streamId"
        element={
          <ProtectedRoute allow={['active']}>
            <LivePage />
          </ProtectedRoute>
        }
      />

      <Route path="admin/login" element={<AdminLoginPage />} />
      <Route element={<AdminRoute />}>
        <Route element={<AdminLayout />}>
          <Route path="admin" element={<AdminReviewsPage />} />
          <Route path="admin/admins" element={<AdminAccountsPage />} />
          <Route path="admin/audit" element={<AdminAuditPage />} />
          <Route path="admin/coin-pricing" element={<AdminCoinPricingPage />} />
        </Route>
      </Route>
    </Routes>
  )
}
