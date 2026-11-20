package net.munea.app.debugbridge;

import android.app.Activity;
import android.app.Application;
import android.content.ContentProvider;
import android.content.ContentValues;
import android.database.Cursor;
import android.net.Uri;
import android.os.Bundle;
import android.webkit.WebView;

import com.getcapacitor.BridgeActivity;

import java.lang.ref.WeakReference;

/** debug 包專用：App 行程一起來就記住目前的 BridgeActivity，讓 DebugEvalReceiver 找得到 WebView。 */
public class DebugBridgeProvider extends ContentProvider {
    private static WeakReference<BridgeActivity> current = new WeakReference<>(null);

    static WebView webView() {
        BridgeActivity a = current.get();
        if (a == null || a.getBridge() == null) return null;
        return a.getBridge().getWebView();
    }

    @Override
    public boolean onCreate() {
        Application app = (Application) getContext().getApplicationContext();
        app.registerActivityLifecycleCallbacks(new Application.ActivityLifecycleCallbacks() {
            @Override public void onActivityCreated(Activity a, Bundle b) { if (a instanceof BridgeActivity) current = new WeakReference<>((BridgeActivity) a); }
            @Override public void onActivityStarted(Activity a) { if (a instanceof BridgeActivity) current = new WeakReference<>((BridgeActivity) a); }
            @Override public void onActivityResumed(Activity a) { if (a instanceof BridgeActivity) current = new WeakReference<>((BridgeActivity) a); }
            @Override public void onActivityPaused(Activity a) {}
            @Override public void onActivityStopped(Activity a) {}
            @Override public void onActivitySaveInstanceState(Activity a, Bundle b) {}
            @Override public void onActivityDestroyed(Activity a) {}
        });
        return true;
    }

    @Override public Cursor query(Uri u, String[] p, String s, String[] a, String o) { return null; }
    @Override public String getType(Uri u) { return null; }
    @Override public Uri insert(Uri u, ContentValues v) { return null; }
    @Override public int delete(Uri u, String s, String[] a) { return 0; }
    @Override public int update(Uri u, ContentValues v, String s, String[] a) { return 0; }
}
