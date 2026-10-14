using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;

namespace Gateway.Demo.Tests
{
    // Test-only process handles. Terminate always uses a retained kernel handle,
    // never a process name or a PID that may have been recycled.
    public sealed class ConsoleProcess : IDisposable
    {
        private IntPtr handle;
        public uint ProcessId { get; private set; }
        public DateTime CreatedUtc { get; private set; }

        private ConsoleProcess(IntPtr value, uint id)
        {
            handle = value;
            ProcessId = id;
            long created, exited, kernel, user;
            if (!GetProcessTimes(handle, out created, out exited, out kernel, out user))
                throw new Win32Exception(Marshal.GetLastWin32Error());
            CreatedUtc = DateTime.FromFileTimeUtc(created);
        }

        public bool HasExited { get { return WaitForSingleObject(handle, 0) == 0; } }
        public uint ExitCode
        {
            get
            {
                uint value;
                if (!GetExitCodeProcess(handle, out value))
                    throw new Win32Exception(Marshal.GetLastWin32Error());
                return value;
            }
        }

        public bool Wait(int milliseconds)
        {
            return WaitForSingleObject(handle, (uint)milliseconds) == 0;
        }

        public void Terminate()
        {
            if (!HasExited && !TerminateProcess(handle, 137))
                throw new Win32Exception(Marshal.GetLastWin32Error());
        }

        public static ConsoleProcess Open(uint id)
        {
            IntPtr value = OpenProcess(0x00100000 | 0x1000 | 0x0001, false, id);
            if (value == IntPtr.Zero)
                throw new Win32Exception(Marshal.GetLastWin32Error());
            try { return new ConsoleProcess(value, id); }
            catch { CloseHandle(value); throw; }
        }

        public static ConsoleProcess Start(string executable, string arguments,
            string workingDirectory, string outputPath, bool separateConsole)
        {
            SECURITY_ATTRIBUTES security = new SECURITY_ATTRIBUTES();
            security.length = Marshal.SizeOf(typeof(SECURITY_ATTRIBUTES));
            security.inheritHandle = true;
            IntPtr output = CreateFile(outputPath, 0x40000000, 0x00000001 | 0x00000002,
                ref security, 2, 0x80, IntPtr.Zero);
            if (output == new IntPtr(-1))
                throw new Win32Exception(Marshal.GetLastWin32Error());
            IntPtr input = CreateFile("NUL", 0x80000000, 0x00000001 | 0x00000002,
                ref security, 3, 0x80, IntPtr.Zero);
            if (input == new IntPtr(-1))
            {
                CloseHandle(output);
                throw new Win32Exception(Marshal.GetLastWin32Error());
            }
            try
            {
                STARTUPINFO startup = new STARTUPINFO();
                startup.size = Marshal.SizeOf(typeof(STARTUPINFO));
                startup.flags = 0x00000100 | 0x00000001; // USESTDHANDLES | USESHOWWINDOW
                startup.showWindow = 0; // SW_HIDE; an actual console still exists.
                startup.standardInput = input;
                startup.standardOutput = output;
                startup.standardError = output;
                PROCESS_INFORMATION process;
                StringBuilder command = new StringBuilder("\"" + executable + "\" " + arguments);
                uint flags = separateConsole ? 0x00000010u : 0x08000000u;
                if (!CreateProcess(executable, command, IntPtr.Zero, IntPtr.Zero,
                    true, flags, IntPtr.Zero, workingDirectory, ref startup, out process))
                    throw new Win32Exception(Marshal.GetLastWin32Error());
                CloseHandle(process.thread);
                try { return new ConsoleProcess(process.process, process.id); }
                catch
                {
                    TerminateProcess(process.process, 137);
                    CloseHandle(process.process);
                    throw;
                }
            }
            finally
            {
                CloseHandle(input);
                CloseHandle(output);
            }
        }

        // Called only from a separate helper process. It cannot detach the
        // invoking test shell, or signal a user's existing terminal.
        public static void SendCtrlC(uint runnerId)
        {
            FreeConsole();
            if (!AttachConsole(runnerId))
                throw new Win32Exception(Marshal.GetLastWin32Error());
            try
            {
                // AttachConsole resets handlers. Ignore Ctrl+C only in this helper.
                if (!SetConsoleCtrlHandler(IntPtr.Zero, true))
                    throw new Win32Exception(Marshal.GetLastWin32Error());
                // CTRL_C_EVENT cannot target a nonzero process group.
                if (!GenerateConsoleCtrlEvent(0, 0))
                    throw new Win32Exception(Marshal.GetLastWin32Error());
                System.Threading.Thread.Sleep(250);
            }
            finally { FreeConsole(); }
        }

        public void Dispose()
        {
            if (handle != IntPtr.Zero) { CloseHandle(handle); handle = IntPtr.Zero; }
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct SECURITY_ATTRIBUTES
        {
            public int length;
            public IntPtr descriptor;
            [MarshalAs(UnmanagedType.Bool)] public bool inheritHandle;
        }
        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        private struct STARTUPINFO
        {
            public int size;
            public string reserved, desktop, title;
            public uint x, y, xSize, ySize, xCountChars, yCountChars, fillAttribute, flags;
            public ushort showWindow, reserved2Size;
            public IntPtr reserved2, standardInput, standardOutput, standardError;
        }
        [StructLayout(LayoutKind.Sequential)]
        private struct PROCESS_INFORMATION
        {
            public IntPtr process, thread;
            public uint id, threadId;
        }

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true,
            EntryPoint = "CreateProcessW")]
        private static extern bool CreateProcess(string application, StringBuilder command,
            IntPtr processAttributes, IntPtr threadAttributes, bool inheritHandles,
            uint flags, IntPtr environment, string directory,
            ref STARTUPINFO startup, out PROCESS_INFORMATION process);
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true,
            EntryPoint = "CreateFileW")]
        private static extern IntPtr CreateFile(string file, uint access, uint share,
            ref SECURITY_ATTRIBUTES security, uint disposition, uint attributes, IntPtr template);
        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern IntPtr OpenProcess(uint access, bool inheritHandle, uint id);
        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool GetProcessTimes(IntPtr process, out long created,
            out long exited, out long kernel, out long user);
        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool GetExitCodeProcess(IntPtr process, out uint code);
        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool TerminateProcess(IntPtr process, uint code);
        [DllImport("kernel32.dll")] private static extern uint WaitForSingleObject(IntPtr handle, uint milliseconds);
        [DllImport("kernel32.dll")] private static extern bool CloseHandle(IntPtr handle);
        [DllImport("kernel32.dll", SetLastError = true)] private static extern bool AttachConsole(uint id);
        [DllImport("kernel32.dll")] private static extern bool FreeConsole();
        [DllImport("kernel32.dll", SetLastError = true)] private static extern bool SetConsoleCtrlHandler(IntPtr handler, bool add);
        [DllImport("kernel32.dll", SetLastError = true)] private static extern bool GenerateConsoleCtrlEvent(uint signal, uint group);
    }
}
