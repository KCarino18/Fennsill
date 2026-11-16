using FennsillAgent;
using Microsoft.Extensions.Hosting.WindowsServices;

InstallPaths.ApplyProcessEnvironment();

var builder = Host.CreateApplicationBuilder(args);
builder.Services.AddWindowsService(options =>
{
    options.ServiceName = InstallPaths.ServiceName;
});
builder.Services.AddHostedService<CloudAgentHostedService>();

var host = builder.Build();
host.Run();
