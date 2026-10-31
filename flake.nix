{
  description = "Skald - Arctic Oral Companion & Multi-Chapter M4B Audiobook Compiler";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
    prism = {
      url = "github:SpanishSyntax/Prism";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = {
    self,
    nixpkgs,
    flake-utils,
    prism,
  }: let
    systems = flake-utils.lib.defaultSystems;
  in
    flake-utils.lib.eachSystem systems (system: let
      pkgs = import nixpkgs {
        inherit system;
        overlays = [prism.overlays.default];
      };
      lib = pkgs.lib;

      skaldPackage = pkgs.python3Packages.buildPythonApplication {
        pname = "skald";
        version = "0.1.0";
        src = lib.cleanSource ./.;
        pyproject = true;

        build-system = [
          pkgs.python3Packages.setuptools
        ];

        propagatedBuildInputs = [
          pkgs.python3Packages.prism
          pkgs.python3Packages.edge-tts
          pkgs.python3Packages.mutagen
          pkgs.python3Packages.pydub
        ];

        nativeBuildInputs = [
          pkgs.makeWrapper
        ];

        postFixup = ''
          wrapProgram $out/bin/skald \
            --prefix PATH : ${lib.makeBinPath [pkgs.ffmpeg]}
        '';

        nativeCheckInputs = [
          pkgs.python3Packages.pytest
        ];

        doCheck = false;

        meta = with lib; {
          description = "Frost-native oral lecture companion & M4B audiobook compiler";
          homepage = "https://github.com/SpanishSyntax/Skald";
          license = licenses.mit;
          mainProgram = "skald";
        };
      };
    in {
      packages = {
        default = skaldPackage;
        skald = skaldPackage;
      };

      apps = {
        default = {
          type = "app";
          program = "${skaldPackage}/bin/skald";
        };
        skald = {
          type = "app";
          program = "${skaldPackage}/bin/skald";
        };
      };

      devShells.default = pkgs.mkShell {
        packages = [
          (pkgs.python3.withPackages (ps: [
            ps.setuptools
            ps.pytest
            ps.prism
            ps.edge-tts
            ps.mutagen
            ps.pydub
          ]))
          pkgs.ffmpeg
        ];
      };
    })
    // {
      overlays = {
        default = final: prev: {
          skald = self.packages.${prev.stdenv.hostPlatform.system}.default;
        };
        skald = self.overlays.default;
      };

      nixosModules = {
        default = self.nixosModules.skald;
        skald = {
          config,
          lib,
          pkgs,
          ...
        }: let
          cfg = config.programs.skald;
          system = pkgs.stdenv.hostPlatform.system;
        in {
          options.programs.skald = {
            enable = lib.mkEnableOption "Skald - Arctic oral companion & audiobook compiler";
            package = lib.mkOption {
              type = lib.types.package;
              default = self.packages.${system}.default;
              description = "The Skald package to install system-wide.";
            };
          };
          config = lib.mkIf cfg.enable {
            environment.systemPackages = [cfg.package];
          };
        };
      };

      homeManagerModules = {
        default = self.homeManagerModules.skald;
        skald = {
          config,
          lib,
          pkgs,
          ...
        }: let
          cfg = config.programs.skald;
          tomlFormat = pkgs.formats.toml {};
          system = pkgs.stdenv.hostPlatform.system;
          defaultSkald = self.packages.${system}.default;
        in {
          options.programs.skald = {
            enable = lib.mkEnableOption "Skald - Arctic oral companion & audiobook compiler";

            package = lib.mkOption {
              type = lib.types.package;
              default = defaultSkald;
              description = "The Skald package to use.";
            };

            settings = lib.mkOption {
              type = tomlFormat.type;
              default = {};
              description = "Configuration written to ~/.config/skald/skald.toml.";
            };
          };

          config = lib.mkIf cfg.enable {
            home.packages = [cfg.package];
            xdg.configFile."skald/skald.toml" = lib.mkIf (cfg.settings != {}) {
              source = tomlFormat.generate "skald.toml" cfg.settings;
            };
          };
        };
      };
    };
}
