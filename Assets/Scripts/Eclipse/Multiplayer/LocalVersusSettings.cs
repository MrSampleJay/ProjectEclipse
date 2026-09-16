using System;

namespace Eclipse.Multiplayer
{
    /// <summary>Immutable configuration for one local match and its rematches.</summary>
    public sealed class LocalVersusSettings
    {
        public string PlayerOneWeapon { get; }
        public string PlayerTwoWeapon { get; }
        public string Location { get; }
        public bool KeyboardPlayerOne { get; }
        public int WinsRequired { get; }
        public int RoundTimeSeconds { get; }

        public LocalVersusSettings(string playerOneWeapon, string playerTwoWeapon, string location,
            bool keyboardPlayerOne, int winsRequired = 2, int roundTimeSeconds = 99)
        {
            if (string.IsNullOrWhiteSpace(playerOneWeapon)) throw new ArgumentException("Choose player one's weapon.", nameof(playerOneWeapon));
            if (string.IsNullOrWhiteSpace(playerTwoWeapon)) throw new ArgumentException("Choose player two's weapon.", nameof(playerTwoWeapon));
            if (string.IsNullOrWhiteSpace(location)) throw new ArgumentException("Choose an arena.", nameof(location));
            if (winsRequired < 1 || winsRequired > 5) throw new ArgumentOutOfRangeException(nameof(winsRequired));
            if (roundTimeSeconds < 30 || roundTimeSeconds > 300) throw new ArgumentOutOfRangeException(nameof(roundTimeSeconds));
            PlayerOneWeapon = playerOneWeapon;
            PlayerTwoWeapon = playerTwoWeapon;
            Location = location;
            KeyboardPlayerOne = keyboardPlayerOne;
            WinsRequired = winsRequired;
            RoundTimeSeconds = roundTimeSeconds;
        }
    }

    public static class LocalVersusRoundRules
    {
        /// <returns>Zero for player one, one for player two, or minus one for a draw.</returns>
        public static int ResolveWinner(float playerOneHealthFraction, float playerTwoHealthFraction)
        {
            if (float.IsNaN(playerOneHealthFraction) || float.IsInfinity(playerOneHealthFraction) ||
                float.IsNaN(playerTwoHealthFraction) || float.IsInfinity(playerTwoHealthFraction))
                throw new ArgumentException("Round health must be finite.");
            float difference = playerOneHealthFraction - playerTwoHealthFraction;
            // Equal timeouts and double knockouts never award a round to either side.
            if (Math.Abs(difference) <= 0.000001f) return -1;
            return difference > 0 ? 0 : 1;
        }
    }
}
