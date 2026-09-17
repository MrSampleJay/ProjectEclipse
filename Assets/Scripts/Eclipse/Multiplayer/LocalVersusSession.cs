using System;
using Eclipse.Input;
using Nekki.SF2.Core.Fights.Controller;
using UnityEngine;

namespace Eclipse.Multiplayer
{
    /// <summary>Owns the lifetime of local play, including boot, pause and results.</summary>
    public sealed class LocalVersusSession : MonoBehaviour
    {
        public static bool IsActive { get; private set; }
        public static bool IsReady { get; private set; }
        public static LocalVersusSettings Settings { get; private set; }
        public static bool HasResult { get; private set; }
        private static LocalVersusSession _instance;
        private static bool _starting;
        private static bool _returning;
        private static float _startedAt;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        private static void ResetSession()
        {
            IsActive = IsReady = HasResult = _starting = _returning = false;
            Settings = null;
            _instance = null;
        }

        public static void RequestEntry()
        {
            IsActive = true;
            IsReady = HasResult = false;
        }

        public static void DataReady()
        {
            if (!IsActive) return;
            IsReady = true;
            if (_instance == null)
            {
                _instance = new GameObject("Eclipse Local Versus Session").AddComponent<LocalVersusSession>();
                DontDestroyOnLoad(_instance.gameObject);
            }
            LocalVersusMenu.Ensure().ShowLobby();
        }

        public static bool DevicesReady(bool keyboardPlayerOne)
        {
            return FightGamepadInput.IsConnected(GamePad.Player.One) &&
                (keyboardPlayerOne || FightGamepadInput.IsConnected(GamePad.Player.Two));
        }

        public static void StartMatch(LocalVersusSettings settings)
        {
            if (!IsActive || !IsReady || _starting || _returning)
                throw new InvalidOperationException("Local versus is not ready to start.");
            if (settings == null) throw new ArgumentNullException(nameof(settings));
            if (!DevicesReady(settings.KeyboardPlayerOne))
                throw new InvalidOperationException(settings.KeyboardPlayerOne ? "Connect a gamepad for player two." : "Connect two gamepads.");
            var current = Fight.GetCurrentFight();
            if (current != null && !current.IsLocalVersus)
                throw new InvalidOperationException("Leave the current fight before starting local versus.");
            // Validate and prepare both independent loadouts before leaving the lobby.
            var match = new LocalVersusMatch(settings);
            current?.SetPaused(true);
            Settings = settings;
            HasResult = false;
            _starting = true;
            _startedAt = Time.realtimeSinceStartup;
            LocalVersusMenu.Ensure().Hide();
            try { Module.GetInstance().OpenLocalVersus(match); }
            catch
            {
                _starting = false;
                LocalVersusMenu.Ensure().ShowLobby();
                throw;
            }
        }

        internal static void FightReady(Fight fight)
        {
            if (fight == null || !fight.IsLocalVersus) throw new ArgumentException("Expected a local fight.");
            _starting = false;
            HasResult = false;
        }

        public static void Pause(string reason)
        {
            var fight = Fight.GetCurrentFight();
            if (!IsActive || _starting || HasResult || fight == null || !fight.IsLocalVersus) return;
            fight.SetPaused(true);
            LocalVersusMenu.Ensure().ShowPause(reason);
        }

        public static void Resume()
        {
            var fight = Fight.GetCurrentFight();
            if (!IsActive || HasResult || _starting || fight == null || !fight.IsLocalVersus) return;
            if (!DevicesReady(Settings.KeyboardPlayerOne))
            {
                LocalVersusMenu.Ensure().ShowPause("Reconnect the assigned controllers to continue.");
                return;
            }
            LocalVersusMenu.Ensure().Hide();
            fight.SetPaused(false);
        }

        public static void ShowLobby()
        {
            if (!IsActive || !IsReady || _starting || _returning) return;
            var fight = Fight.GetCurrentFight();
            if (fight != null && fight.IsLocalVersus) fight.SetPaused(true);
            LocalVersusMenu.Ensure().ShowLobby();
        }

        internal static void Complete(Fight fight, bool abandoned = false)
        {
            if (HasResult || fight == null || !fight.IsLocalVersus) return;
            HasResult = true;
            fight.SetPaused(true);
            int one = fight.GetPlayerModel().Parameters.RoundsWon;
            int two = fight.GetEnemyModel().Parameters.RoundsWon;
            LocalVersusMenu.Ensure().ShowResult(abandoned ? -1 : (one > two ? 0 : 1), one, two);
        }

        public static void ReturnToTitle()
        {
            if (_returning) return;
            _returning = true;
            Fight.GetCurrentFight()?.SetPaused(true);
            GameController.get_Current()?.StopController();
            LocalVersusMenu.Ensure().Hide();
            Eclipse.UI.TitleScreen.PrepareForRestart();
            Sound.StopLoopedSounds();
            Time.timeScale = 1f;
            // Keep isolation active until the outgoing scene has completed teardown.
            SceneManagerSF.Load(ScreenType.ModulePreloader);
        }

        internal static void ArrivedAtTitle()
        {
            if (!_returning) return;
            var menu = UnityEngine.Object.FindFirstObjectByType<LocalVersusMenu>();
            if (menu != null) Destroy(menu.gameObject);
            if (_instance != null) Destroy(_instance.gameObject);
            ResetSession();
        }

        private void OnApplicationFocus(bool focused)
        {
            if (!focused) Pause("The game lost focus. Resume when both players are ready.");
        }

        private void Update()
        {
            if (!IsActive || _returning) return;
            if (_starting)
            {
                if (Time.realtimeSinceStartup - _startedAt > 45f)
                {
                    _starting = false;
                    Debug.LogError("[Local Versus] The fight scene did not finish loading.");
                    LocalVersusMenu.Ensure().ShowPause("The match could not load. Return to the title screen and try again.");
                }
                return;
            }
            var fight = Fight.GetCurrentFight();
            if (Settings != null && fight != null && fight.IsLocalVersus && !HasResult && !fight.IsPaused() &&
                !DevicesReady(Settings.KeyboardPlayerOne)) Pause("A controller disconnected. Reconnect it, then resume.");
        }
    }
}
