package com.apkcleaner.studio;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.ViewTreeObserver;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.view.animation.AccelerateDecelerateInterpolator;
import android.view.animation.DecelerateInterpolator;
import android.view.animation.OvershootInterpolator;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;

public final class LauncherActivity extends Activity {
    private final Handler handler = new Handler(Looper.getMainLooper());
    private long launchStartedAt;
    private long animationStartedAt;
    private Runnable splashAnimation;
    private boolean splashAnimationStarted;

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        launchStartedAt = SystemClock.uptimeMillis();
        if (Build.VERSION.SDK_INT >= 31) {
            // Remove the mandatory system cover without a second logo/fade animation.
            getSplashScreen().setOnExitAnimationListener(splash -> {
                splash.remove();
                startSplashAnimation();
            });
        }
        getWindow().setStatusBarColor(getColor(R.color.splash_background_color));
        getWindow().setNavigationBarColor(getColor(R.color.splash_background_color));
        buildSplash();
        applySplashSystemBars();
        Intent service = new Intent(this, EngineService.class);
        if (Build.VERSION.SDK_INT >= 26) startForegroundService(service); else startService(service);
        handler.post(this::awaitEngine);
    }

    private void buildSplash() {
        FrameLayout root = new FrameLayout(this);
        root.setBackgroundResource(R.drawable.splash_background);
        root.setOnApplyWindowInsetsListener((view, insets) -> {
            int top;
            int bottom;
            if (Build.VERSION.SDK_INT >= 30) {
                android.graphics.Insets bars = insets.getInsets(
                        WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout());
                top = bars.top;
                bottom = bars.bottom;
            } else {
                top = insets.getSystemWindowInsetTop();
                bottom = insets.getSystemWindowInsetBottom();
            }
            view.setPadding(0, top, 0, bottom);
            return insets;
        });

        LinearLayout content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setGravity(Gravity.CENTER);
        content.setAlpha(0f);
        content.setTranslationY(dp(18));

        FrameLayout emblem = new FrameLayout(this);
        LinearLayout.LayoutParams emblemParams = new LinearLayout.LayoutParams(dp(142), dp(142));
        emblemParams.bottomMargin = dp(28);
        content.addView(emblem, emblemParams);

        // Logo çevresinde genel amaçlı halkalar yerine markanın kendi kare
        // karakterini öne çıkaran yumuşak bir ışık alanı kullan.
        View logoGlow = new View(this);
        GradientDrawable glowShape = new GradientDrawable();
        glowShape.setShape(GradientDrawable.OVAL);
        glowShape.setGradientType(GradientDrawable.RADIAL_GRADIENT);
        glowShape.setGradientRadius(dp(70));
        glowShape.setColors(new int[] {getColor(R.color.splash_glow), Color.TRANSPARENT});
        logoGlow.setBackground(glowShape);
        logoGlow.setAlpha(0f);
        emblem.addView(logoGlow, new FrameLayout.LayoutParams(dp(140), dp(140), Gravity.CENTER));

        ImageView icon = new ImageView(this);
        icon.setImageResource(R.mipmap.ic_launcher);
        icon.setScaleType(ImageView.ScaleType.CENTER_INSIDE);
        icon.setScaleX(.72f);
        icon.setScaleY(.72f);
        icon.setRotation(-4f);
        icon.setAlpha(0f);
        emblem.addView(icon, new FrameLayout.LayoutParams(dp(112), dp(112), Gravity.CENTER));

        TextView title = new TextView(this);
        title.setText(R.string.app_name);
        title.setTextColor(getColor(R.color.splash_title));
        title.setTextSize(25);
        title.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        title.setGravity(Gravity.CENTER);
        content.addView(title, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        TextView tagline = new TextView(this);
        tagline.setText(R.string.splash_tagline);
        tagline.setTextColor(getColor(R.color.splash_tagline));
        tagline.setTextSize(11);
        tagline.setLetterSpacing(.16f);
        tagline.setAllCaps(true);
        tagline.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams tagParams = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        tagParams.topMargin = dp(9);
        content.addView(tagline, tagParams);

        View progress = new View(this);
        GradientDrawable progressShape = new GradientDrawable(
                GradientDrawable.Orientation.LEFT_RIGHT,
                new int[] {Color.rgb(45, 205, 157), Color.rgb(196, 255, 43)});
        progressShape.setCornerRadius(dp(2));
        progress.setBackground(progressShape);
        progress.setPivotX(0f);
        progress.setScaleX(0f);
        LinearLayout.LayoutParams progressParams = new LinearLayout.LayoutParams(dp(92), dp(3));
        progressParams.topMargin = dp(24);
        content.addView(progress, progressParams);

        root.addView(content, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        setContentView(root);
        root.requestApplyInsets();
        splashAnimation = () -> {
            content.animate().alpha(1f).translationY(0f).setDuration(430)
                .setInterpolator(new DecelerateInterpolator()).start();
            icon.animate().scaleX(1f).scaleY(1f).rotation(0f).alpha(1f).setDuration(620)
                .setInterpolator(new OvershootInterpolator(.58f)).start();
            logoGlow.animate().scaleX(1f).scaleY(1f).alpha(.34f).setStartDelay(90).setDuration(720)
                .setInterpolator(new DecelerateInterpolator()).start();
            progress.animate().scaleX(1f).setStartDelay(170).setDuration(760)
                .setInterpolator(new AccelerateDecelerateInterpolator()).start();
        };
        logoGlow.setScaleX(.68f);
        logoGlow.setScaleY(.68f);
        root.getViewTreeObserver().addOnPreDrawListener(new ViewTreeObserver.OnPreDrawListener() {
            @Override public boolean onPreDraw() {
                root.getViewTreeObserver().removeOnPreDrawListener(this);
                // Prepare the animation for this first draw, not one frame later.
                // The system exit callback and this fallback share the once-only guard.
                startSplashAnimation();
                return true;
            }
        });
    }

    private void startSplashAnimation() {
        if (splashAnimationStarted || splashAnimation == null || isFinishing() || isDestroyed()) return;
        splashAnimationStarted = true;
        animationStartedAt = SystemClock.uptimeMillis();
        Runnable animation = splashAnimation;
        splashAnimation = null;
        animation.run();
    }

    private void applySplashSystemBars() {
        boolean light = getResources().getBoolean(R.bool.splash_light_bars);
        if (Build.VERSION.SDK_INT >= 30) {
            WindowInsetsController controller = getWindow().getDecorView().getWindowInsetsController();
            int mask = WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS | WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS;
            if (controller != null) controller.setSystemBarsAppearance(light ? mask : 0, mask);
        } else {
            int mask = View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR;
            if (Build.VERSION.SDK_INT >= 27) mask |= View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR;
            int flags = getWindow().getDecorView().getSystemUiVisibility();
            getWindow().getDecorView().setSystemUiVisibility(light ? flags | mask : flags & ~mask);
        }
    }

    private void awaitEngine() {
        long now = SystemClock.uptimeMillis();
        long visibleElapsed = splashAnimationStarted ? now - animationStartedAt : 0;
        if ((EngineService.ready && splashAnimationStarted && visibleElapsed >= 720)
                || now - launchStartedAt >= 30000 || !EngineService.startupError.isEmpty()) {
            startActivity(new Intent(this, MainActivity.class)
                    .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP));
            overridePendingTransition(android.R.anim.fade_in, android.R.anim.fade_out);
            finish();
            return;
        }
        handler.postDelayed(this::awaitEngine, 70);
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    @Override protected void onDestroy() {
        splashAnimation = null;
        handler.removeCallbacksAndMessages(null);
        super.onDestroy();
    }
}
