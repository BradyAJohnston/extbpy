"""
Core builder functionality for extbpy.
"""

import glob
import os
import subprocess
import sys
import shutil
import logging
from pathlib import Path
from typing import List, Dict, Any, Set, Optional, Union
import tomlkit

from .platforms import Platform, get_platforms, detect_current_platform
from .exceptions import (
    ExtbpyError, 
    ConfigurationError, 
    DependencyError, 
    BuildError, 
    BlenderError
)

logger = logging.getLogger(__name__)

class ExtensionBuilder:
    """Main builder class for Blender extensions."""
    
    def __init__(
        self,
        source_dir: Path,
        output_dir: Optional[Path] = None,
        python_version: str = "3.11",
        excluded_packages: Optional[Set[str]] = None
    ):
        self.source_dir = Path(source_dir).resolve()
        self.output_dir = Path(output_dir or Path.cwd()).resolve()
        self.python_version = python_version
        self.excluded_packages = excluded_packages or {
            "pyarrow", "certifi", "charset_normalizer", "idna", 
            "numpy", "requests", "urllib3"
        }
        
        # Validate source directory structure
        self._validate_source_dir()
        
        # Set up paths
        self.extension_dir = self._find_extension_dir()
        self.wheels_dir = self.extension_dir / "wheels"
        self.manifest_path = self.extension_dir / "blender_manifest.toml"
        self.pyproject_path = self.source_dir / "pyproject.toml"
        
        # Load project configuration
        self.project_config = self._load_project_config()
        
    def _validate_source_dir(self) -> None:
        """Validate that source directory exists and has required structure."""
        if not self.source_dir.exists():
            raise ConfigurationError(f"Source directory does not exist: {self.source_dir}")
        
        pyproject_path = self.source_dir / "pyproject.toml"
        if not pyproject_path.exists():
            raise ConfigurationError(f"No pyproject.toml found in {self.source_dir}")
            
    def _find_extension_dir(self) -> Path:
        """Find the extension directory within source directory."""
        # Look for directories with blender_manifest.toml
        for item in self.source_dir.iterdir():
            if item.is_dir():
                manifest_path = item / "blender_manifest.toml"
                if manifest_path.exists():
                    return item
        
        # Fallback: look for common extension directory names
        for name in ["extension", "addon", "warbler"]:
            candidate = self.source_dir / name
            if candidate.exists() and candidate.is_dir():
                return candidate
                
        raise ConfigurationError(
            f"No extension directory found in {self.source_dir}. "
            "Expected a directory containing blender_manifest.toml"
        )
    
    def _load_project_config(self) -> Dict[str, Any]:
        """Load and validate project configuration."""
        try:
            with open(self.pyproject_path, 'r', encoding='utf-8') as f:
                config = tomlkit.parse(f.read())
                
            # Validate required sections
            if 'project' not in config:
                raise ConfigurationError("No [project] section in pyproject.toml")
                
            project = config['project']
            if 'dependencies' not in project:
                logger.warning("No dependencies found in pyproject.toml")
                project['dependencies'] = []
                
            return config
            
        except FileNotFoundError:
            raise ConfigurationError(f"pyproject.toml not found: {self.pyproject_path}")
        except Exception as e:
            raise ConfigurationError(f"Error reading pyproject.toml: {e}")
    
    def get_project_info(self) -> Dict[str, Any]:
        """Get project information for display."""
        project = self.project_config.get('project', {})
        return {
            'name': project.get('name', 'Unknown'),
            'version': project.get('version', 'Unknown'),
            'description': project.get('description', 'No description'),
            'dependencies': project.get('dependencies', []),
            'extension_dir': str(self.extension_dir),
            'wheels_dir': str(self.wheels_dir),
        }
    
    def detect_current_platform(self) -> List[str]:
        """Detect current platform."""
        return detect_current_platform()
    
    def _run_python_command(self, args: List[str]) -> None:
        """Run a Python command with proper error handling."""
        python_exe = sys.executable
        cmd = [python_exe] + args
        
        logger.debug(f"Running command: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd, 
                check=True, 
                capture_output=True, 
                text=True,
                cwd=self.source_dir
            )
            
            if result.stdout:
                logger.debug(f"Command output: {result.stdout}")
                
        except subprocess.CalledProcessError as e:
            logger.error(f"Command failed: {' '.join(cmd)}")
            logger.error(f"Exit code: {e.returncode}")
            logger.error(f"Stdout: {e.stdout}")
            logger.error(f"Stderr: {e.stderr}")
            raise DependencyError(f"Python command failed: {e.stderr or e.stdout}")
    
    def _ensure_tomlkit_available(self) -> None:
        """Ensure tomlkit is available, install if needed."""
        try:
            import tomlkit
        except ImportError:
            logger.info("Installing tomlkit...")
            self._run_python_command(["-m", "pip", "install", "tomlkit"])
            import tomlkit
    
    def download_wheels(
        self, 
        platforms: List[str], 
        clean: bool = True,
        ignore_platform_errors: bool = True
    ) -> List[str]:
        """Download wheels for specified platforms."""
        self._ensure_tomlkit_available()
        
        platform_objects = get_platforms(platforms)
        dependencies = self.project_config['project']['dependencies']
        
        if not dependencies:
            logger.warning("No dependencies to download")
            return
        
        # Create wheels directory
        self.wheels_dir.mkdir(parents=True, exist_ok=True)
        
        if clean:
            self._clean_wheels_dir()
        
        logger.info(f"Downloading wheels for platforms: {', '.join(platforms)}")
        logger.info(f"Dependencies: {', '.join(dependencies)}")
        
        failed_platforms = []
        successful_platforms = []
        
        for platform_obj in platform_objects:
            logger.info(f"Downloading wheels for {platform_obj.name}...")
            
            cmd = [
                "-m", "pip", "download",
                *dependencies,
                "--dest", str(self.wheels_dir),
                "--only-binary=:all:",
                f"--python-version={self.python_version}",
                f"--platform={platform_obj.pypi_suffix}"
            ]
            
            try:
                self._run_python_command(cmd)
                successful_platforms.append(platform_obj.name)
                logger.info(f"✅ Successfully downloaded wheels for {platform_obj.name}")
            except DependencyError as e:
                failed_platforms.append(platform_obj.name)
                logger.error(f"❌ Failed to download wheels for {platform_obj.name}: {e}")
                
        if failed_platforms and not successful_platforms:
            raise DependencyError(f"Failed to download wheels for all platforms: {', '.join(failed_platforms)}")
        elif failed_platforms:
            if ignore_platform_errors:
                logger.warning(f"Some platforms failed: {', '.join(failed_platforms)}. Continuing with: {', '.join(successful_platforms)}")
            else:
                raise DependencyError(f"Failed to download wheels for platforms: {', '.join(failed_platforms)}")
            
        return successful_platforms
    
    def _clean_wheels_dir(self) -> None:
        """Clean the wheels directory."""
        if self.wheels_dir.exists():
            shutil.rmtree(self.wheels_dir)
        self.wheels_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Cleaned wheels directory: {self.wheels_dir}")
    
    def _filter_wheels(self) -> List[Path]:
        """Filter out excluded packages from wheels."""
        wheel_files = list(self.wheels_dir.glob("*.whl"))
        wheel_files.sort()
        
        to_keep = []
        to_remove = []
        
        for whl_path in wheel_files:
            whl_name = whl_path.name.lower()
            should_exclude = any(
                pkg.lower() in whl_name for pkg in self.excluded_packages
            )
            
            if should_exclude:
                to_remove.append(whl_path)
                logger.debug(f"Excluding wheel: {whl_path.name}")
            else:
                to_keep.append(whl_path)
        
        # Remove excluded wheels
        for whl_path in to_remove:
            whl_path.unlink()
            logger.debug(f"Removed excluded wheel: {whl_path.name}")
        
        logger.info(f"Keeping {len(to_keep)} wheels, removed {len(to_remove)} excluded wheels")
        return to_keep
    
    def update_manifest(self, platforms: List[str]) -> None:
        """Update the Blender manifest with wheels and platform info."""
        platform_objects = get_platforms(platforms)
        wheel_files = self._filter_wheels()
        
        # Load existing manifest or create new one
        if self.manifest_path.exists():
            with open(self.manifest_path, 'r', encoding='utf-8') as f:
                manifest = tomlkit.parse(f.read())
        else:
            manifest = tomlkit.document()
            logger.warning(f"Creating new manifest at {self.manifest_path}")
        
        # Update wheels list
        wheel_paths = [f"./wheels/{whl.name}" for whl in wheel_files]
        manifest["wheels"] = wheel_paths
        
        # Update platforms
        platform_names = [p.metadata for p in platform_objects]
        manifest["platforms"] = platform_names
        
        logger.info(f"Updated manifest with {len(wheel_paths)} wheels for platforms: {', '.join(platform_names)}")
        
        # Write updated manifest with nice formatting
        with open(self.manifest_path, 'w', encoding='utf-8') as f:
            content = tomlkit.dumps(manifest)
            # Format arrays nicely
            content = (content
                       .replace('["', '[\n\t"')
                       .replace('", "', '",\n\t"')
                       .replace('"]', '",\n]')
                       .replace('\\\\', '/'))
            f.write(content)
    
    def clean_files(self, patterns: List[str] = None) -> int:
        """Clean temporary files from extension directory."""
        if patterns is None:
            patterns = [".blend1", ".MNSession"]
        
        cleaned_count = 0
        
        for pattern in patterns:
            pattern_path = f"**/*{pattern}"
            for file_path in self.extension_dir.rglob(pattern_path):
                if file_path.is_file():
                    file_path.unlink()
                    logger.debug(f"Removed: {file_path}")
                    cleaned_count += 1
        
        logger.info(f"Cleaned {cleaned_count} temporary files")
        return cleaned_count
    
    def _find_blender_executable(self) -> str:
        """Find Blender executable."""
        try:
            import bpy
            return bpy.app.binary_path
        except ImportError:
            # Try to find Blender in PATH
            blender_names = ["blender", "blender.exe"]
            for name in blender_names:
                if shutil.which(name):
                    return shutil.which(name)
            
            raise BlenderError(
                "Blender executable not found. Please ensure Blender is installed "
                "and available in PATH, or run this tool from within Blender."
            )
    
    def build_extension(self, split_platforms: bool = True) -> None:
        """Build the Blender extension."""
        # Clean temporary files first
        self.clean_files()
        
        blender_exe = self._find_blender_executable()
        
        cmd = [
            blender_exe,
            "--command", "extension", "build",
            "--source-dir", str(self.extension_dir),
            "--output-dir", str(self.output_dir)
        ]
        
        if split_platforms:
            cmd.append("--split-platforms")
        
        logger.info(f"Building extension with command: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
                cwd=self.source_dir
            )
            
            if result.stdout:
                logger.info(f"Build output: {result.stdout}")
                
        except subprocess.CalledProcessError as e:
            logger.error(f"Build failed: {e.stderr}")
            raise BuildError(f"Extension build failed: {e.stderr or 'Unknown error'}")
    
    def build(
        self, 
        platforms: List[str], 
        clean: bool = True, 
        split_platforms: bool = True,
        ignore_platform_errors: bool = True
    ) -> None:
        """Complete build process: download wheels, update manifest, and build extension."""
        logger.info(f"Starting build for platforms: {', '.join(platforms)}")
        
        try:
            # Download wheels for all platforms
            successful_platforms = self.download_wheels(platforms, clean=clean, ignore_platform_errors=ignore_platform_errors)
            
            if not successful_platforms:
                raise BuildError("No platforms were successfully processed")
            
            # Update manifest with wheels and platform info for successful platforms only
            self.update_manifest(successful_platforms)
            
            # Build the extension
            self.build_extension(split_platforms=split_platforms)
            
            logger.info(f"Build completed successfully for platforms: {', '.join(successful_platforms)}")
            
        except Exception as e:
            logger.error(f"Build failed: {e}")
            raise