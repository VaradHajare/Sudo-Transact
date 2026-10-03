/*
 * AI Resolve demo app (Expo). A thin native shell around the web app in ../web, so the phone shows
 * exactly what the laptop shows: Scan & Pay, the agents' investigation, voice, the language toggle.
 *
 * The backend runs on the laptop. The phone reaches it through an HTTPS tunnel (cloudflared): the
 * browser engine only allows the microphone on HTTPS. The tunnel address changes on every run, so
 * it is entered once here and remembered.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { requestRecordingPermissionsAsync } from 'expo-audio';
import { StatusBar } from 'expo-status-bar';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator, BackHandler, KeyboardAvoidingView, Linking, Platform, Pressable, StyleSheet, Text, TextInput,
  View,
} from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';
import { WebView } from 'react-native-webview';

const STORAGE_KEY = 'server_url';
const COLORS = { navy: '#002970', sky: '#00baf2', bg: '#f5f7fa', text: '#101828', muted: '#667085', danger: '#d92d20' };

/** "abc.trycloudflare.com/" -> "https://abc.trycloudflare.com" */
function normalize(input) {
  let url = input.trim().replace(/\/+$/, '');
  if (url && !/^https?:\/\//i.test(url)) url = `https://${url}`;
  return url;
}

async function checkServer(url) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 8000);
  try {
    const res = await fetch(`${url}/healthz`, { signal: ctrl.signal });
    const body = await res.json();
    if (!body.ok) throw new Error('The server answered, but not like the AI Resolve backend.');
    return body;
  } finally {
    clearTimeout(timer);
  }
}

/** First screen: where the laptop's backend is (the cloudflared https address). */
function ServerScreen({ initialUrl, onConnect }) {
  const [url, setUrl] = useState(initialUrl || '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function connect() {
    const target = normalize(url);
    if (!target) return;
    setBusy(true);
    setError(null);
    try {
      await checkServer(target);
      await AsyncStorage.setItem(STORAGE_KEY, target);
      onConnect(target);
    } catch (e) {
      setError(e.name === 'AbortError' ? 'No answer in 8 seconds. Is the backend and the tunnel running?' : String(e.message || e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <SafeAreaView style={styles.setup}>
      <StatusBar style="light" />
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={styles.setupInner}>
        <Text style={styles.title}>AI Resolve</Text>
        <Text style={styles.subtitle}>Prototype · mock data, no real money</Text>
        <View style={styles.card}>
          <Text style={styles.label}>Server address</Text>
          <TextInput
            style={styles.input}
            value={url}
            onChangeText={setUrl}
            placeholder="https://something.trycloudflare.com"
            placeholderTextColor={COLORS.muted}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="url"
            returnKeyType="go"
            onSubmitEditing={connect}
          />
          {url && /^http:\/\//i.test(url.trim()) && !/localhost|127\.0\.0\.1/.test(url) ? (
            <Text style={styles.warn}>Plain http works for reading, but the phone's mic needs https.</Text>
          ) : null}
          {error ? <Text style={styles.error}>{error}</Text> : null}
          <Pressable style={[styles.button, busy && styles.buttonBusy]} onPress={connect} disabled={busy}>
            {busy ? <ActivityIndicator color="#fff" /> : <Text style={styles.buttonText}>Connect</Text>}
          </Pressable>
        </View>
        <Text style={styles.help}>
          On the laptop, start the backend, then run{'\n'}
          <Text style={styles.code}>cloudflared tunnel --url http://localhost:8000</Text>
          {'\n'}and paste the https address it prints.
        </Text>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

/** The web app, full screen. Android back = back in the app; at its home screen, back to the server screen. */
function AppScreen({ url, onChangeServer }) {
  const web = useRef(null);
  const canGoBack = useRef(false);
  const [failed, setFailed] = useState(null);

  useEffect(() => {
    const sub = BackHandler.addEventListener('hardwareBackPress', () => {
      if (canGoBack.current && web.current) {
        web.current.goBack();
        return true;
      }
      onChangeServer();
      return true;
    });
    return () => sub.remove();
  }, [onChangeServer]);

  if (failed) {
    return (
      <SafeAreaView style={styles.setup}>
        <StatusBar style="light" />
        <View style={styles.setupInner}>
          <Text style={styles.title}>Can't reach the server</Text>
          <Text style={styles.subtitle}>{failed}</Text>
          <Pressable style={styles.button} onPress={() => setFailed(null)}>
            <Text style={styles.buttonText}>Retry</Text>
          </Pressable>
          <Pressable style={styles.linkButton} onPress={onChangeServer}>
            <Text style={styles.link}>Change server address</Text>
          </Pressable>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.app} edges={['top', 'bottom']}>
      <StatusBar style="light" backgroundColor={COLORS.navy} />
      <WebView
        ref={web}
        source={{ uri: `${url}/#/` }}
        style={styles.web}
        javaScriptEnabled
        domStorageEnabled
        // spoken replies start by themselves (after the user's own taps), like in Chrome
        mediaPlaybackRequiresUserAction={false}
        allowsInlineMediaPlayback
        // the page asks for the mic with getUserMedia; the app already holds the permission
        mediaCapturePermissionGrantType="grant"
        setSupportMultipleWindows={false}
        overScrollMode="never"
        startInLoadingState
        renderLoading={() => (
          <View style={styles.loading}><ActivityIndicator size="large" color={COLORS.sky} /></View>
        )}
        // "Talk to a human" rings the support line: tel: links go to the phone's dialer.
        onShouldStartLoadWithRequest={(req) => {
          if (/^(tel|sms|mailto):/i.test(req.url)) {
            Linking.openURL(req.url).catch(() => {});
            return false;
          }
          return true;
        }}
        onNavigationStateChange={(nav) => { canGoBack.current = nav.canGoBack; }}
        onError={(e) => setFailed(e.nativeEvent.description || 'The page could not be loaded.')}
        onHttpError={(e) => { if (e.nativeEvent.statusCode >= 500) setFailed(`Server error ${e.nativeEvent.statusCode}.`); }}
      />
    </SafeAreaView>
  );
}

export default function App() {
  const [url, setUrl] = useState(null);
  const [ready, setReady] = useState(false);
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    (async () => {
      // Ask once, up front: the in-app mic button then works without a second prompt.
      try { await requestRecordingPermissionsAsync(); } catch { /* text mode still works */ }
      setUrl(await AsyncStorage.getItem(STORAGE_KEY));
      setReady(true);
    })();
  }, []);

  const changeServer = useCallback(() => setEditing(true), []);

  if (!ready) {
    return <View style={[styles.loading, { backgroundColor: COLORS.navy }]}><ActivityIndicator color="#fff" /></View>;
  }
  return (
    <SafeAreaProvider>
      {url && !editing
        ? <AppScreen url={url} onChangeServer={changeServer} />
        : <ServerScreen initialUrl={url} onConnect={(u) => { setUrl(u); setEditing(false); }} />}
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  app: { flex: 1, backgroundColor: COLORS.navy },
  web: { flex: 1, backgroundColor: COLORS.bg },
  loading: { ...StyleSheet.absoluteFillObject, alignItems: 'center', justifyContent: 'center', backgroundColor: COLORS.bg },
  setup: { flex: 1, backgroundColor: COLORS.navy },
  setupInner: { flex: 1, justifyContent: 'center', padding: 24 },
  title: { color: '#fff', fontSize: 28, fontWeight: '800' },
  subtitle: { color: 'rgba(255,255,255,0.75)', fontSize: 14, marginTop: 4, marginBottom: 24 },
  card: { backgroundColor: '#fff', borderRadius: 16, padding: 16 },
  label: { color: COLORS.muted, fontSize: 13, marginBottom: 8 },
  input: {
    borderWidth: 1, borderColor: '#e4e7ec', borderRadius: 12, paddingHorizontal: 14, paddingVertical: 12,
    fontSize: 16, color: COLORS.text, backgroundColor: COLORS.bg,
  },
  warn: { color: '#b54708', fontSize: 13, marginTop: 8 },
  error: { color: COLORS.danger, fontSize: 13, marginTop: 8 },
  button: { marginTop: 16, backgroundColor: COLORS.navy, borderRadius: 999, paddingVertical: 14, alignItems: 'center' },
  buttonBusy: { opacity: 0.7 },
  buttonText: { color: '#fff', fontWeight: '700', fontSize: 16 },
  linkButton: { marginTop: 12, alignItems: 'center', padding: 8 },
  link: { color: COLORS.sky, fontWeight: '600' },
  help: { color: 'rgba(255,255,255,0.8)', fontSize: 13, lineHeight: 20, marginTop: 20 },
  code: { fontFamily: Platform.select({ android: 'monospace', ios: 'Menlo' }), color: '#fff' },
});
